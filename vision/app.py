import json
import os
import threading
import time

import cv2
import paho.mqtt.client as mqtt
import uvicorn
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from ultralytics import YOLO

from logic import categorize

CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", "0"))
MQTT_HOST = os.environ.get("MQTT_HOST", "localhost")
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))
TABLE_ID = os.environ.get("TABLE_ID", "table1")
TOPIC = f"sentinelx/{TABLE_ID}/vision"
PUBLISH_INTERVAL = 5.0
STREAM_PORT = int(os.environ.get("STREAM_PORT", "8001"))

COLORS = {"person": (0, 0, 255), "animal": (255, 200, 0)}

frame_lock = threading.Lock()
latest_jpeg: bytes | None = None

app = FastAPI(title="SENTINEL-X Vision")


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


def capture_loop(model: YOLO, client: mqtt.Client) -> None:
    global latest_jpeg
    cap = cv2.VideoCapture(CAMERA_INDEX, getattr(cv2, "CAP_DSHOW", cv2.CAP_ANY))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    last_publish = 0.0
    frames, debut_mesure = 0, time.time()

    while True:
        ok, frame = cap.read()
        if not ok:
            time.sleep(1)
            continue

        result = model(frame, verbose=False)[0]
        frames += 1
        if time.time() - debut_mesure >= 5.0:
            print(f"{frames / (time.time() - debut_mesure):.1f} images/s")
            frames, debut_mesure = 0, time.time()
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

            now = time.time()
            if category == "person" and now - last_publish >= PUBLISH_INTERVAL:
                client.publish(TOPIC, json.dumps({"label": "person", "confidence": round(confidence, 2)}))
                last_publish = now

        ok, jpg = cv2.imencode(".jpg", frame)
        if ok:
            with frame_lock:
                latest_jpeg = jpg.tobytes()


def main() -> None:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.connect(MQTT_HOST, MQTT_PORT)
    client.loop_start()

    model = YOLO("yolov8n.pt")
    threading.Thread(target=capture_loop, args=(model, client), daemon=True).start()
    uvicorn.run(app, host="0.0.0.0", port=STREAM_PORT)


if __name__ == "__main__":
    main()
