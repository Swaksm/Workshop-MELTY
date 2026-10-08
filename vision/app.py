import base64
import json
import os
import sys
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from ultralytics import YOLO

from logic import categorize

CAMERA_BACKEND = getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY)
MAX_CAMERAS = 5
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TABLE_ID = os.environ.get("TABLE_ID", "table1")
TOPIC = f"sentinelx/{TABLE_ID}/vision"
PRESENCE_SECONDS = 3.0
ABSENCE_SECONDS = 2.0
CLIP_SECONDS = 5.0
CLIP_SIZE = (320, 240)
MEDIA_DIR = Path(os.environ.get("MEDIA_DIR", Path(__file__).resolve().parent.parent / "media"))
STREAM_PORT = int(os.environ.get("STREAM_PORT", "8001"))
# Boucle locale uniquement : depuis le réseau, le flux passe par le proxy HTTPS,
# qui vérifie la session avant de laisser passer (pas d'accès direct sans mot de passe)
STREAM_HOST = os.environ.get("STREAM_HOST", "127.0.0.1")

COLORS = {"person": (0, 0, 255), "animal": (255, 200, 0)}

state_lock = threading.Lock()
frame_lock = threading.Lock()
latest_jpeg: bytes | None = None
available_cameras: list[int] = []
camera_index = int(os.environ.get("CAMERA_INDEX", "0"))
presence_status = {"progression": 0.0, "confirmee": False}

app = FastAPI(title="SENTINEL-X Vision")


class CameraIn(BaseModel):
    index: int = Field(ge=0, lt=MAX_CAMERAS)


@app.get("/stream")
def stream():
    def frames():
        while True:
            with frame_lock:
                jpeg = latest_jpeg
            if jpeg is not None:
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n"
            time.sleep(0.05)

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/cameras")
def cameras() -> dict:
    with state_lock:
        return {"disponibles": available_cameras, "active": camera_index}


@app.get("/presence")
def presence() -> dict:
    with state_lock:
        return dict(presence_status)


@app.post("/camera")
def choose_camera(body: CameraIn) -> dict:
    global camera_index
    if body.index not in available_cameras:
        raise HTTPException(status_code=404, detail=f"Caméra {body.index} introuvable")
    with state_lock:
        camera_index = body.index
    return {"active": body.index}


def probe_cameras(ignorer: int | None = None) -> list[int]:
    found = []
    for index in range(MAX_CAMERAS):
        if index == ignorer:
            found.append(index)
            continue
        cap = cv2.VideoCapture(index, CAMERA_BACKEND)
        if cap.isOpened() and cap.read()[0]:
            found.append(index)
        cap.release()
    return found


def probe_loop() -> None:
    """Re-sonde les caméras en arrière-plan : une webcam branchée après le démarrage
    devient disponible sans relancer le process. N'ouvre jamais l'index actif, déjà
    utilisé par capture_loop (deux VideoCapture sur le même index se gênent)."""
    while True:
        time.sleep(5)
        with state_lock:
            actif = camera_index
        trouvees = sorted(probe_cameras(ignorer=actif))
        with state_lock:
            available_cameras[:] = trouvees


def open_camera(index: int) -> cv2.VideoCapture:
    cap = cv2.VideoCapture(index, CAMERA_BACKEND)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    return cap


class PresenceTracker:
    def __init__(self) -> None:
        self.premiere_vue: float | None = None
        self.derniere_vue: float | None = None
        self.alerte_envoyee = False
        self.progression = 0.0

    def mettre_a_jour(self, personne_presente: bool, maintenant: float) -> bool:
        if personne_presente:
            self.derniere_vue = maintenant
            if self.premiere_vue is None:
                self.premiere_vue = maintenant
            self.progression = min(1.0, (maintenant - self.premiere_vue) / PRESENCE_SECONDS)
            if not self.alerte_envoyee and self.progression >= 1.0:
                self.alerte_envoyee = True
                return True
            return False
        self.progression = 0.0
        if self.derniere_vue is not None and maintenant - self.derniere_vue >= ABSENCE_SECONDS:
            self.premiere_vue = None
            self.derniere_vue = None
            self.alerte_envoyee = False
        return False


def ecrire_clip(enregistrement: dict, client: mqtt.Client) -> None:
    frames = enregistrement["frames"]
    duree = max(frames[-1][0] - frames[0][0], 0.1)
    fps = min(max(len(frames) / duree, 3.0), 15.0)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    nom = f"clip_{TABLE_ID}_{int(enregistrement['debut'])}.mp4"
    writer = cv2.VideoWriter(str(MEDIA_DIR / nom), cv2.VideoWriter_fourcc(*"avc1"), fps, CLIP_SIZE)
    for _, image in frames:
        writer.write(image)
    writer.release()

    payload = {
        "label": "person",
        "confidence": round(enregistrement["confiance"], 2),
        "image": base64.b64encode(enregistrement["jpg"]).decode("ascii"),
        "clip": nom,
    }
    client.publish(TOPIC, json.dumps(payload))


def capture_loop(model: YOLO, client: mqtt.Client) -> None:
    global latest_jpeg
    cap = None
    opened = None
    presence = PresenceTracker()
    tampon: deque = deque()
    enregistrement: dict | None = None
    frames, debut_mesure = 0, time.time()
    echecs_lecture = 0

    while True:
        with state_lock:
            wanted = camera_index
        if wanted != opened:
            if cap is not None:
                cap.release()
            cap = open_camera(wanted)
            opened = wanted
            frames, debut_mesure = 0, time.time()
            presence = PresenceTracker()
            tampon.clear()
            enregistrement = None

        ok, frame = cap.read()
        if not ok:
            echecs_lecture += 1
            if echecs_lecture >= 10:
                print(f"Caméra {opened} ne répond plus, réouverture...")
                cap.release()
                cap = open_camera(opened)
                echecs_lecture = 0
            time.sleep(1)
            continue
        echecs_lecture = 0

        result = model(frame, verbose=False)[0]
        frames += 1
        if time.time() - debut_mesure >= 5.0:
            print(f"{frames / (time.time() - debut_mesure):.1f} images/s")
            frames, debut_mesure = 0, time.time()

        meilleure_personne = None
        for box in result.boxes:
            label = model.names[int(box.cls)]
            confidence = float(box.conf)
            category = categorize(label, confidence)
            if category is None:
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            color = COLORS[category]
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, f"{label} {confidence:.0%}", (x1, max(y1 - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
            if category == "person" and (meilleure_personne is None or confidence > meilleure_personne):
                meilleure_personne = confidence

        maintenant = time.time()
        declencher = presence.mettre_a_jour(meilleure_personne is not None, maintenant)
        with state_lock:
            presence_status["progression"] = round(presence.progression, 3)
            presence_status["confirmee"] = presence.alerte_envoyee

        ok, jpg = cv2.imencode(".jpg", frame)
        if not ok:
            continue
        with frame_lock:
            latest_jpeg = jpg.tobytes()

        petite = cv2.resize(frame, CLIP_SIZE)
        tampon.append((maintenant, petite))
        while tampon and maintenant - tampon[0][0] > CLIP_SECONDS:
            tampon.popleft()

        if declencher and enregistrement is None:
            enregistrement = {
                "debut": maintenant,
                "frames": list(tampon),
                "jpg": jpg.tobytes(),
                "confiance": meilleure_personne,
            }
        elif enregistrement is not None:
            enregistrement["frames"].append((maintenant, petite))
            if maintenant - enregistrement["debut"] >= CLIP_SECONDS:
                threading.Thread(target=ecrire_clip, args=(enregistrement, client), daemon=True).start()
                enregistrement = None


def main() -> None:
    global available_cameras, camera_index

    available_cameras = probe_cameras()
    if not available_cameras:
        sys.exit("Aucune webcam détectée.")
    if camera_index not in available_cameras:
        camera_index = available_cameras[0]
    print(f"Caméras disponibles : {available_cameras}")

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(os.environ.get("VISION_MQTT_USER", "vision"), os.environ.get("VISION_MQTT_PASSWORD", ""))
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()

    model = YOLO("yolov8n.pt")
    threading.Thread(target=capture_loop, args=(model, client), daemon=True).start()
    threading.Thread(target=probe_loop, daemon=True).start()
    uvicorn.run(app, host=STREAM_HOST, port=STREAM_PORT)


if __name__ == "__main__":
    main()
