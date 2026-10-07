# SENTINEL-X

Surveillance d'une table : un ESP32 relève température, humidité et gaz, un modèle d'IA détecte les anomalies, une webcam repère les personnes, un buzzer alerte sur place, un mail part vers l'équipe et un dashboard affiche l'état en temps réel.

Projet du workshop EPSI Bac+4 (mission AetherCorp). Le sujet impose notamment : pas de seuils statiques, chiffrement des flux, stack conteneurisée, aucun secret dans l'archive du code.

## Sommaire

1. [Architecture](#1-architecture)
2. [Stack](#2-stack)
3. [Structure du dépôt](#3-structure-du-dépôt)
4. [Installation et lancement](#4-installation-et-lancement)
5. [Réseau de la table](#5-réseau-de-la-table)
6. [Configuration](#6-configuration)
7. [Flux de données](#7-flux-de-données)
8. [Protocole MQTT](#8-protocole-mqtt)
9. [Base de données](#9-base-de-données)
10. [API REST et Swagger](#10-api-rest-et-swagger)
11. [Modèle d'IA des capteurs](#11-modèle-dia-des-capteurs)
12. [Surveillance vidéo](#12-surveillance-vidéo)
13. [Alertes par mail](#13-alertes-par-mail)
14. [Tests et CI/CD](#14-tests-et-cicd)
15. [Simulateur](#15-simulateur)
16. [Limites connues](#16-limites-connues)
17. [Feuille de route](#17-feuille-de-route)

## 1. Architecture

```
                         ┌──────────────── PC serveur (192.168.52.1) ────────────────┐
ESP32 (192.168.52.50)    │                                                          │
 DHT22 · MQ-2 · buzzer   │  Docker Compose                                          │
        │                │   ┌───────────┐   ┌──────────┐   ┌────────────┐          │
        │ MQTT 1883      │   │ mosquitto │◄──┤ backend  │──►│ PostgreSQL │          │
        └───────────────►│   │  :1883    │──►│ FastAPI  │   │   :5432    │          │
                         │   └───────────┘   │  :8000   │   └────────────┘          │
Webcam USB (PC)          │        ▲          └────┬─────┘                           │
   │                     │        │ MQTT            │ SMTP (Gmail)                   │
   ▼                     │   ┌────┴───────────┐     ▼                                │
 vision/app.py ──────────┼──►│ vision (hors   │   Boîte mail de l'équipe             │
 YOLOv8 nano · :8001     │   │ Docker, sur PC)│                                      │
                         │   └────────────────┘                                      │
                         └──────────────────────────────────────────────────────────┘
                                         ▲                    ▲
                    dashboard React (Vite, :5173) ── proxy /api → :8000, /vision → :8001
                                         ▲
                              navigateur (PC ou autre appareil du hotspot)
```

- Les **capteurs** passent par MQTT, puis le backend les enregistre et évalue le modèle d'IA.
- La **vidéo** passe par le module vision, qui tourne sur le PC et non dans Docker : un conteneur Windows n'accède pas à la webcam USB.
- Les **alertes** déclenchent le buzzer et, au plus une fois toutes les 5 minutes, un mail.

## 2. Stack

| Couche | Technologies |
|---|---|
| Firmware | C++ (Arduino, ESP32), ArduinoOTA, PubSubClient, ArduinoJson, DHT |
| Broker | Eclipse Mosquitto 2 |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, paho-mqtt 2, scikit-learn 1.6 |
| Vision | Python 3.10, Ultralytics YOLOv8 nano, OpenCV 4.10, FastAPI |
| Base de données | PostgreSQL 16 |
| Frontend | React 18, Vite 5, Recharts |
| Mails | SMTP Gmail (mot de passe d'application) |
| Tests et CI | pytest, GitHub Actions, GHCR |
| Infra | Docker Compose |

## 3. Structure du dépôt

```
.
├── backend/
│   ├── app/
│   │   ├── main.py          # routes FastAPI et cycle de vie (MQTT, tables)
│   │   ├── mqtt.py          # abonnements capteurs et vision, publication des commandes
│   │   ├── detection.py     # évaluation d'une mesure (LOF), alerte capteurs, buzzer, mail
│   │   ├── ml_temp.py       # Random Forest de tendance de température (entraîné sur données simulées)
│   │   ├── detection_temp.py # alerte de hausse de température

│   │   ├── vision.py        # détection de personne : enregistrement, buzzer, mail
│   │   ├── ml.py            # features, entraînement et chargement du modèle capteurs
│   │   ├── notifier.py      # envoi des mails, délai de 5 minutes
│   │   ├── alerts_mail.py   # construction des mails (HTML et texte)
│   │   ├── models.py        # tables measurements, alerts, detections
│   │   ├── schemas.py       # schémas Pydantic d'entrée et de sortie
│   │   ├── db.py            # moteur et session SQLAlchemy
│   │   └── config.py        # variables d'environnement
│   ├── tests/               # pytest : modèle, API, détection, vision, mails
│   ├── Dockerfile
│   ├── pytest.ini
│   ├── requirements.txt
│   └── requirements-dev.txt
├── vision/                  # module vision, lancé sur le PC (hors Docker)
│   ├── app.py               # webcam, YOLO, présence, flux MJPEG, API caméras
│   ├── logic.py             # règle de classement : personne, animal, autre
│   ├── tests/               # pytest de la règle de classement
│   ├── pytest.ini
│   └── requirements.txt
├── frontend/
│   ├── src/main.jsx         # point d'entrée, bascule entre connexion et supervision
│   ├── src/Login.jsx        # écran de connexion
│   ├── src/auth.js          # identifiants et session (sessionStorage)
│   ├── src/App.jsx          # écran de supervision
│   ├── src/api.js           # appels à l'API et au module vision
│   ├── src/styles.css
│   └── vite.config.js       # proxy /api → :8000 et /vision → :8001
├── firmware/
│   └── sentinel_wifi/sentinel_wifi.ino  # connexion WiFi en IP fixe, OTA
├── mosquitto/
│   └── mosquitto.conf       # configuration du broker (développement)
├── tools/
│   └── simulate_sensors.py  # publie de fausses mesures sur le broker
├── media/                   # clips vidéo des détections (ignoré par Git, créé au premier clip)
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
└── README.md
```

## 4. Installation et lancement

### Lancement rapide (Windows)

Une seule commande démarre tout : Docker Desktop si besoin, la stack (base, broker, backend), le dashboard et le module vision.

```powershell
powershell -ExecutionPolicy Bypass -File .\lancer.ps1
```

Options : `-CameraIndex 1` pour une autre webcam, `-SansVision` ou `-SansFront` pour ne pas lancer une partie.

Pour tout arrêter (la base et les modèles sont conservés) :

```powershell
powershell -ExecutionPolicy Bypass -File .\arreter.ps1
```

Les journaux sont dans le dossier `logs\`. Le détail manuel ci-dessous reste valable.

### Prérequis

- Docker Desktop (ou Docker Engine et Compose v2)
- Node.js 20 ou plus, pour le frontend
- Python 3.10 pour le module vision, avec une webcam
- Un Wi-Fi 2,4 GHz pour l'ESP32 (voir [Réseau de la table](#5-réseau-de-la-table))

### Lancer le back

```bash
git clone https://github.com/Swaksm/Workshop-MELTY.git
cd Workshop-MELTY
cp .env.example .env          # puis complète les variables mail (section 6)
docker compose up --build -d
curl http://localhost:8000/health   # {"status":"ok"}
```

| Service | Port hôte | Rôle |
|---|---|---|
| `backend` | 8000 | API REST et Swagger, liée à `127.0.0.1` et à `HOTSPOT_IP` (les autres appareils de la table) |
| `mosquitto` | 1883 et 8883 | broker MQTT : 1883 en clair sur `127.0.0.1` (backend, vision), 8883 en TLS sur `127.0.0.1` et `HOTSPOT_IP` (ESP32) |
| `db` | non exposé | PostgreSQL, réseau Docker uniquement |

Les conteneurs tournent sous un utilisateur non-root, sans privilèges supplémentaires et avec système de fichiers en lecture seule (sauf les volumes de données). `lancer.ps1` détecte l'adresse du hotspot et la met dans `HOTSPOT_IP` du `.env`.

### Lancer le dashboard

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Ouvre http://localhost:5173.

### Lancer le module vision (sur le PC, hors Docker)

```powershell
cd vision
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
.venv\Scripts\python.exe -m pip install -r requirements.txt
$env:CAMERA_INDEX = "0"
.venv\Scripts\python.exe app.py
```

Le premier lancement télécharge les poids `yolov8n.pt` (environ 6 Mo), donc il faut une connexion internet. Le module liste les caméras au démarrage : si tu branches une webcam après, il faut le relancer.

### Arrêter

```bash
docker compose down        # garde les données (base, modèles)
docker compose down -v     # supprime aussi la base et les modèles entraînés
```

## 5. Réseau de la table

Le PC serveur et l'ESP32 sont sur le **Wi-Fi du labo** (`WIFI_LABO`), pas sur un hotspot dédié. Les capteurs et la vidéo restent en local ; seul le MQTT de l'ESP32 est chiffré, puisqu'il transite sur le Wi-Fi partagé de l'école.

### Plan d'adressage

| Équipement | Adresse | Rôle |
|---|---|---|
| PC serveur | DHCP de l'école (ex. `10.0.3.76`) | héberge Mosquitto (1883 local + 8883 TLS) et l'API (8000) |
| ESP32 | DHCP de l'école | publie les mesures en TLS |
| Autres appareils | DHCP de l'école | consultent l'API depuis le navigateur |

L'adresse du PC **change avec le DHCP de l'école**. `lancer.ps1` la détecte à chaque lancement (interface « Wi-Fi ») et la met dans `HOTSPOT_IP` du `.env`. Si elle change, il faut mettre à jour `MQTT_HOST` dans `firmware/sentinel_temp/secrets.h` et reflasher l'ESP32 (OTA possible si le Wi-Fi est encore joignable).

### Se connecter au Wi-Fi du labo

Rien à créer : le PC et l'ESP32 se connectent au Wi-Fi existant de l'école, avec son SSID et son mot de passe. Ces identifiants vont dans `firmware/sentinel_temp/secrets.h` (`WIFI_SSID`, `WIFI_PASSWORD`), jamais dans le dépôt.

### Vérifier l'adresse du PC

```powershell
ipconfig
```

Cherche la carte **Wi-Fi**, section Adresse IPv4. C'est l'adresse à mettre dans `MQTT_HOST`.

### Chiffrement TLS du MQTT

Le broker écoute sur deux ports :

| Port | Chiffrement | Qui l'utilise |
|---|---|---|
| 1883 | aucun | backend et module vision, uniquement via `mosquitto:1883` (réseau Docker interne) et `127.0.0.1:1883` (boucle locale du PC). Jamais exposé sur le Wi-Fi |
| 8883 | TLS 1.2 | ESP32, seul client qui traverse le Wi-Fi du labo |

Les certificats sont générés en local, jamais commités :

```bash
sh mosquitto/gen-certs.sh 10.0.3.76   # adresse du PC, voir ci-dessus
```

Ça produit `mosquitto/certs/{ca.crt,ca.key,server.crt,server.key}`. Pour le firmware, le certificat de la CA doit être copié dans `firmware/sentinel_temp/ca_cert.h` (voir `ca_cert.h.example` pour le format attendu, un `R"EOF(...)EOF"` avec le contenu de `ca.crt`).

`lancer.ps1` recrée aussi `mosquitto/passwd` à chaque lancement à partir des mots de passe du `.env` (`MQTT_PASSWORD`, `VISION_MQTT_PASSWORD`, `ESP32_MQTT_PASSWORD`), donc pas besoin d'y toucher à la main.

### Ouvrir les ports (pare-feu Windows)

Une fois, dans un terminal **administrateur** :

```powershell
New-NetFirewallRule -DisplayName "SENTINEL-X MQTT TLS" -Direction Inbound -Protocol TCP -LocalPort 8883 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "SENTINEL-X API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "SENTINEL-X Vision" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow -Profile Private
```

### Qui parle à qui

| De | Vers | Protocole et port | Usage |
|---|---|---|---|
| ESP32 | PC `MQTT_HOST:8883` | MQTT sur TLS | publie `sentinelx/table1/sensors`, authentifié (`esp32`) |
| Backend (conteneur) | `mosquitto:1883` | MQTT en clair (réseau Docker) | reçoit capteurs et vision, envoie les commandes |
| Backend (conteneur) | `db:5432` | PostgreSQL (réseau Docker) | enregistre les données |
| Vision (PC) | `localhost:1883` | MQTT en clair (boucle locale) | publie `sentinelx/table1/vision` |
| Backend (conteneur) | `smtp.gmail.com:587` | SMTP (STARTTLS) | envoie les mails |
| Navigateur du PC | `localhost:8000`, `localhost:8001` | HTTP | API, Swagger, flux vidéo |
| Autre appareil du Wi-Fi | `HOTSPOT_IP:8000` | HTTP | API et Swagger |

Le backend parle à Mosquitto et à la base par les **noms de service Docker**, pas par l'IP du PC.

### Vérifier que tout communique

```powershell
ipconfig
Test-NetConnection 10.0.3.76 -Port 8883
curl http://localhost:8000/health
```

### Problèmes courants

| Symptôme | Cause probable |
|---|---|
| L'ESP32 se connecte au Wi-Fi, mais `Connexion MQTT... échec` | mauvaise adresse dans `MQTT_HOST` (IP du PC a changé), pare-feu qui bloque 8883, ou identifiants/certificat obsolètes dans `secrets.h`/`ca_cert.h` |
| Les autres appareils n'atteignent pas l'API | pare-feu qui bloque 8000, ou profil réseau « Public » |
| `lancer.ps1` échoue avec « Docker ne répond pas » | Docker Desktop bloqué sur un ancien socket (`%LOCALAPPDATA%\Docker\run`). Redémarre Windows : le verrou disparaît. Ne pas réinitialiser Docker en usine, ça efface les volumes |
| Le backend ne peut pas écrire les modèles (`Permission denied` sur `/code/models`) | le volume `model-data` appartient à root. Le corriger sans rien supprimer : `docker run --rm -v workshop_model-data:/m alpine chown -R 10001:10001 /m` |
| Le module vision ne voit pas une webcam branchée | il ne scanne les caméras qu'au démarrage : relance `lancer.ps1` (ou `arreter.ps1` puis `lancer.ps1`) |
| Mosquitto refuse de démarrer, erreur sur `cafile` | `mosquitto/certs/` absent : lance `sh mosquitto/gen-certs.sh <IP du PC>` avant `lancer.ps1` |

## 6. Configuration

Fichier `.env` à la racine, créé à partir de `.env.example`. Il n'est pas versionné.

| Variable | Exemple | Utilisée par | Rôle |
|---|---|---|---|
| `POSTGRES_USER` | `sentinel` | `db` | utilisateur PostgreSQL |
| `POSTGRES_PASSWORD` | `change-me` | `db` | mot de passe PostgreSQL |
| `POSTGRES_DB` | `sentinel` | `db` | nom de la base |
| `DATABASE_URL` | `postgresql+psycopg://sentinel:…@db:5432/sentinel` | `backend` | connexion SQLAlchemy |
| `MQTT_HOST` | `mosquitto` | `backend` | broker vu depuis le backend |
| `MQTT_PORT` | `1883` | `backend` | port MQTT |
| `HOTSPOT_IP` | `192.168.52.1` | `docker compose` | adresse du PC sur le hotspot, où l'ESP32 joint le broker et l'API. Mise à jour automatiquement par `lancer.ps1` (`127.0.0.1` si le hotspot est éteint) |
| `GMAIL_USER` | `adresse@gmail.com` | `backend` | compte qui envoie les mails |
| `GMAIL_APP_PASSWORD` | `abcdefghijklmnop` | `backend` | mot de passe d'application Google (16 caractères, sans espaces) |
| `ALERT_TO` | `equipe@exemple.com` | `backend` | destinataire des alertes |
| `MEDIA_DIR` | `media` | `backend` | dossier des clips vidéo, partagé avec le module vision |

Si `GMAIL_USER`, `GMAIL_APP_PASSWORD` ou `ALERT_TO` manque, les mails sont désactivés sans erreur : les alertes restent dans la base, le buzzer fonctionne toujours.

Variables du module vision (lues par `vision/app.py`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `CAMERA_INDEX` | `0` | webcam de départ (on peut changer depuis le dashboard) |
| `MQTT_HOST` | `localhost` | broker MQTT |
| `MQTT_PORT` | `1883` | port MQTT |
| `TABLE_ID` | `table1` | table à laquelle rattacher les détections |
| `STREAM_PORT` | `8001` | port de l'API et du flux vidéo |
| `MEDIA_DIR` | dossier `media/` du dépôt | où écrire les clips vidéo (le backend lit le même dossier) |

Le `.env` et les mots de passe ne doivent jamais être committés.

## 7. Flux de données

### Capteurs

1. L'ESP32 lit le DHT22 et le MQ-2, et publie un JSON sur `sentinelx/<table>/sensors` toutes les 5 s.
2. Le backend valide le message (`temp` et `hum` en nombres, `gas` en entier) et l'insère dans `measurements`.
3. Si le modèle de la table existe, il évalue les 30 dernières mesures (voir [section 11](#11-modèle-dia-des-capteurs)).
4. Au passage en anomalie : une ligne dans `alerts` (type `anomalie`), `buzzer on`, et un mail si le délai de 5 minutes est écoulé.
5. Une tendance à la hausse de température, détectée par le Random Forest : une ligne dans `alerts` (type `hausse_temperature`), `buzzer on`, et un mail avec son propre délai (voir [section 11](#11-modèle-dia-des-capteurs)).
5. Au retour à la normale : `buzzer off`.

### Vidéo

1. Le module vision lit la webcam, lance YOLOv8 nano sur chaque image et dessine les cadres : rouge pour une personne, orange pour un animal.
2. Une personne doit rester visible **3 secondes** pour être confirmée. Elle doit disparaître **2 secondes** pour que la règle se réarme.
3. Le module garde en mémoire les 5 dernières secondes d'images. À la confirmation, il continue d'enregistrer 5 secondes de plus, puis écrit un clip MP4 (320×240) dans `media/`.
4. Il publie sur `sentinelx/<table>/vision` le label, la confiance, la capture annotée (JPEG en base64) et le nom du clip.
5. Le backend enregistre la détection dans `detections`, active le buzzer pendant 10 s, et envoie un mail si le délai de 5 minutes est écoulé. Le mail joint la capture, et la vidéo si le total reste sous 20 Mo.

### Commandes

Le backend publie `{"buzzer":"on"}` ou `{"buzzer":"off"}` sur `sentinelx/<table>/cmd`. L'ESP32 doit s'abonner à ce topic pour agir : ce n'est pas encore dans le firmware.

### Cas d'erreur

| Situation | Comportement |
|---|---|
| Payload invalide (JSON, champ manquant, mauvais type) | message ignoré, warning journalisé |
| `gas` envoyé avec une décimale | rejeté : le champ est un entier |
| Broker indisponible au démarrage | le backend réessaie en tâche de fond |
| Backend redémarré | données conservées, modèles rechargés depuis le disque, état d'alerte remis à zéro |
| Vision arrêtée | pas de détection vidéo, le dashboard affiche « Flux indisponible » |

## 8. Protocole MQTT

Une **table** est un identifiant libre (`table1`). Il doit être identique côté ESP32, vision, backend et dashboard.

| Sens | Topic | Payload | Fréquence |
|---|---|---|---|
| ESP32 → backend | `sentinelx/<table>/sensors` | `{"temp":23.4,"hum":51.2,"gas":1234,"pir":0,"alarm":0}` | toutes les 5 s |
| vision → backend | `sentinelx/<table>/vision` | `{"label":"person","confidence":0.91,"image":"<base64 JPEG>","clip":"clip_table1_...mp4"}` | une fois par présence confirmée, 5 s après la confirmation |
| backend → ESP32 | `sentinelx/<table>/cmd` | `{"buzzer":"on"}` ou `{"buzzer":"off"}` | sur événement |

- `temp` : °C, un chiffre après la virgule. `hum` : humidité relative en %. `gas` : valeur ADC brute, entier de 0 à 4095. `pir` : 0 ou 1, facultatif (mouvement du capteur PIR, stocké dans `measurements.pir`). `alarm` : alarme gaz locale de l'ESP32 (seuil physique sur la carte, pas lié au modèle d'IA) — champ ignoré par le backend pour l'instant.
- Le champ `image` est facultatif. Un label autre que `person` est refusé.
- Le broker refuse les connexions anonymes (`mosquitto/acl`). Backend et vision se connectent en clair sur `1883` (réseau Docker / boucle locale uniquement). L'ESP32 se connecte en **TLS sur `8883`**, authentifié (voir [Réseau de la table](#5-réseau-de-la-table)).

Test manuel depuis le PC, avec les identifiants `esp32` du `.env` :

```bash
mosquitto_sub -h <IP du PC> -p 8883 --cafile mosquitto/certs/ca.crt -u esp32 -P <ESP32_MQTT_PASSWORD> -t "sentinelx/#" -v
mosquitto_pub -h <IP du PC> -p 8883 --cafile mosquitto/certs/ca.crt -u esp32 -P <ESP32_MQTT_PASSWORD> -t "sentinelx/table1/cmd" -m '{"buzzer":"on"}'
```

## 9. Base de données

PostgreSQL 16. Les tables sont créées au démarrage du backend (`create_all`). Il n'y a pas encore de migrations.

### `measurements` : une ligne par mesure capteurs

| Colonne | Type | Contrainte | Description |
|---|---|---|---|
| `id` | `integer` | clé primaire, auto | ordre d'insertion |
| `table_id` | `varchar(64)` | non null, indexée | table émettrice |
| `temp` | `double precision` | non null | température en °C |
| `hum` | `double precision` | non null | humidité en % |
| `gas` | `integer` | non null | valeur ADC brute |
| `received_at` | `timestamptz` | défaut `now()`, indexée | heure de réception |

### `alerts` : une ligne par alerte capteurs

| Colonne | Type | Contrainte | Description |
|---|---|---|---|
| `id` | `integer` | clé primaire, auto | identifiant |
| `table_id` | `varchar(64)` | non null, indexée | table |
| `kind` | `varchar(32)` | défaut `anomalie` | `anomalie` (LOF) ou `hausse_temperature` (Random Forest) |
| `temp`, `hum`, `gas` | `double precision`, `double precision`, `integer` | non null | valeurs de la mesure déclenchante |
| `created_at` | `timestamptz` | défaut `now()`, indexée | heure de l'alerte |

### `detections` : une ligne par personne confirmée

| Colonne | Type | Contrainte | Description |
|---|---|---|---|
| `id` | `integer` | clé primaire, auto | identifiant |
| `table_id` | `varchar(64)` | non null, indexée | table |
| `label` | `varchar(32)` | non null | toujours `person` |
| `confidence` | `double precision` | non null | confiance YOLO, entre 0 et 1 |
| `created_at` | `timestamptz` | défaut `now()`, indexée | heure de la détection |

La capture n'est **pas** stockée en base : elle n'est envoyée que par mail.

### Ce qui n'est pas en base

| Élément | Où | Conséquence |
|---|---|---|
| Modèle capteurs | `backend/models/<table>.joblib` (volume `model-data`) | survit aux redémarrages, pas à `down -v` |
| État « alerte active » | mémoire du backend | repart à faux au redémarrage |
| Délai de 5 minutes des mails | mémoire du backend | repart à zéro au redémarrage |
| Présence vidéo | mémoire du module vision | repart à zéro au redémarrage |

### Volumétrie

Une table à 1 mesure toutes les 5 s produit environ 17 000 lignes par jour dans `measurements`. Il n'y a pas encore de purge.

### Accéder à la base

```bash
docker compose exec db psql -U sentinel -d sentinel
```

```sql
SELECT table_id, count(*) FROM measurements GROUP BY table_id;
SELECT * FROM detections ORDER BY created_at DESC LIMIT 10;
```

## 10. API REST et Swagger

L'API est documentée par FastAPI.

| URL | Contenu |
|---|---|
| http://localhost:8000/docs | **Swagger UI** : routes, schémas, bouton « Try it out » |
| http://localhost:8000/redoc | même documentation, en lecture seule |
| http://localhost:8000/openapi.json | spécification OpenAPI, à importer dans Postman ou un générateur de client |

Base : `http://localhost:8000/api/v1`.

### Routes

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | état du service |
| GET | `/api/v1/mesures?table_id=&limit=` | dernières mesures, plus récentes d'abord (limit max 1000, défaut 100) |
| GET | `/api/v1/alertes?table_id=&limit=` | alertes capteurs (limit max 500, défaut 50) |
| GET | `/api/v1/detections?table_id=&limit=` | personnes détectées (limit max 500, défaut 50) |
| GET | `/api/v1/tables/{table_id}/etat` | `{"alerte_active": bool, "modele_entraine": bool}` |
| POST | `/api/v1/tables/{table_id}/entrainement` | entraîne le modèle capteurs (100 mesures minimum, 5000 au maximum) |
| POST | `/api/v1/tables/{table_id}/commande` | corps `{"buzzer":"on"}` ou `{"buzzer":"off"}`, renvoie 202 |

### Schémas

```json
{"id": 204, "table_id": "table1", "temp": 23.4, "hum": 51.2, "gas": 1234, "received_at": "2026-10-06T07:52:28Z"}
{"id": 3, "table_id": "table1", "temp": 23.1, "hum": 50.2, "gas": 3500, "created_at": "2026-10-06T07:43:45Z"}
{"id": 64, "table_id": "table1", "label": "person", "confidence": 0.89, "created_at": "2026-10-06T14:45:46Z"}
{"alerte_active": true, "modele_entraine": true}
{"mesures_utilisees": 153}
```

### Codes d'erreur

| Code | Quand |
|---|---|
| `400` | entraînement avec moins de 100 mesures |
| `422` | corps ou paramètres invalides |
| `500` | erreur interne, voir les logs du backend |

### Exemples

```bash
curl "http://localhost:8000/api/v1/mesures?table_id=table1&limit=5"
curl "http://localhost:8000/api/v1/detections?table_id=table1"
curl -X POST http://localhost:8000/api/v1/tables/table1/entrainement
curl -X POST http://localhost:8000/api/v1/tables/table1/commande \
     -H "Content-Type: application/json" -d '{"buzzer":"on"}'
```

### API du module vision (port 8001)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/stream` | flux MJPEG avec les cadres dessinés |
| GET | `/cameras` | `{"disponibles": [0, 1], "active": 0}` |
| POST | `/camera` | corps `{"index": 1}` : change de webcam sans redémarrer |
| GET | `/presence` | `{"progression": 0.66, "confirmee": false}` : avancement vers les 3 secondes |

L'API n'a pas d'authentification : elle est prévue pour un usage local, sur le réseau de la table.

## 11. Modèle d'IA des capteurs

Le modèle ne contient aucun seuil écrit à la main. Il apprend ce qui est normal pour une table, puis signale ce qui s'en écarte.

**Entrée.** À chaque mesure, on prend les 30 dernières (environ 2,5 minutes). Cinq valeurs sont calculées : température, humidité et gaz de la mesure courante, plus la pente de la température et du gaz sur la fenêtre (la tendance).

**Algorithme.** Pipeline scikit-learn : `StandardScaler` puis `LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.02)`. Un point est une anomalie s'il se trouve dans une zone beaucoup moins dense que ses 20 voisins appris.

**Entraînement.** `POST /entrainement` lit jusqu'à 5000 mesures, calcule les 5 valeurs pour chacune, entraîne le pipeline et l'enregistre dans `backend/models/<table>.joblib`. Le réentraînement remplace le modèle précédent.

**Bonnes pratiques.** Entraîne sur une période normale : pas de test au gaz, pas de passage devant la caméra, pas de pic simulé. Ce qui est dans les données d'entraînement est appris comme normal.

**Choix du modèle.** Sur des données simulées (avec `contamination=0.05`), Isolation Forest détectait 94 % des pics avec 6,8 % de fausses alertes, et LOF détecte 100 % des pics avec 0,5 % de fausses alertes. `contamination` est passé à `0.02` ensuite, suite à des fausses alertes sur de vraies mesures (un changement normal de 1 °C signalé comme anomalie, baseline trop courte). Les chiffres ci-dessus n'ont pas été remesurés avec ce nouveau réglage.

### Entraînement du modèle capteurs (LOF)

Le modèle capteurs est **entraîné par table**, à la demande :

1. Les 5000 dernières mesures de la table sont lues, dans l'ordre chronologique.
2. Si moins de **100 mesures** sont disponibles, l'entraînement est refusé (HTTP 400).
3. Pour chaque mesure, cinq caractéristiques sont calculées sur une fenêtre glissante de 30 mesures : température, humidité, gaz, pente de la température et pente du gaz.
4. Un pipeline `StandardScaler` puis `LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.02)` est ajusté sur ces valeurs.
5. Le modèle est enregistré dans `backend/models/<table>.joblib`. Un nouvel entraînement remplace le précédent.

Le modèle considère donc que **toutes les mesures d'entraînement sont normales**. Il faut l'entraîner pendant une période calme. Le paramètre `contamination=0.02` signifie que les 2 % de points les plus isolés de la baseline servent de référence pour la frontière.

Lancer l'entraînement :

```bash
curl -X POST http://localhost:8000/api/v1/tables/table1/entrainement
```

### Entraînement du modèle de hausse (Random Forest)

Ce modèle **n'est pas entraîné par table** : il est entraîné une fois, au démarrage du backend, sur des exemples simulés (2000 montées, 2000 stabilités, 1000 descentes). Il n'y a aucune commande à lancer.

### Hausse de température (Random Forest)

Un second modèle surveille uniquement la **tendance** de la température, sans valeur fixe.

- **Entrée** : les 30 dernières températures d'une table. Quatre caractéristiques sont calculées : pente sur la fenêtre, pente sur les 10 dernières mesures, variation totale, écart-type.
- **Modèle** : `RandomForestClassifier` (150 arbres, profondeur 8), entraîné au démarrage du backend.
- **Entraînement** : sur des exemples **simulés** : montées (pentes de 0,03 à 0,3 °C par mesure), stabilités et descentes (classées « pas de hausse »). Ces exemples ne viennent pas de vraies mesures : le modèle ne connaît que ce que la simulation lui a montré.
- **Décision** : une hausse est signalée quand la probabilité dépasse **0,8**. L'alerte se termine quand elle redescend sous **0,5**. Ce ne sont pas des seuils sur la température : ce sont des seuils sur la confiance du modèle, comme pour YOLO.
- **Effet** : une alerte `hausse_temperature`, le buzzer pendant la hausse, et un mail (voir [section 13](#13-alertes-par-mail)).

Le bruit du DHT22 (environ ±0,5 °C) peut masquer une montée lente. Ce modèle doit être réentraîné sur de vraies mesures avant d'être fiable.

### Quand une alerte part

Chaque alerte suit les mêmes principes : elle est créée **au passage** dans l'état d'alerte, puis elle est levée quand le modèle juge la situation revenue à la normale.

| Alerte | Conditions pour déclencher | Fin de l'alerte | Effet |
|---|---|---|---|
| **Anomalie capteurs** (LOF) | un modèle capteurs entraîné pour la table ; une mesure reçue qui tombe hors de la baseline (prédiction `-1`) ; pas déjà en alerte | la mesure suivante est jugée normale | ligne dans `alerts` (type `anomalie`), buzzer `on`, mail si le délai de 5 minutes est écoulé |
| **Hausse de température** (Random Forest) | au moins 30 mesures pour la table ; probabilité de hausse ≥ 0,8 ; pas déjà en alerte | probabilité < 0,5 | ligne dans `alerts` (type `hausse_temperature`), buzzer `on`, mail si le délai de 5 minutes est écoulé |
| **Personne** (vidéo) | présence continue de 3 s ; confiance YOLO ≥ 50 % ; classe `person` uniquement | 2 s d'absence réarment la règle | ligne dans `detections`, buzzer `on` pendant 10 s, mail avec capture et clip si le délai est écoulé |

Points à retenir :
- **Sans modèle entraîné, aucune alerte capteurs** : le LOF n'a pas de baseline à comparer. Le Random Forest de hausse fonctionne dès le démarrage du backend, à condition d'avoir 30 mesures.
- **Un mail par type toutes les 5 minutes** : un événement pendant le délai de son type ne donne pas de mail, mais il reste enregistré et visible sur le dashboard.
- **Le buzzer est partagé** : la fin d'une alerte (ou le buzzer de 10 s de la vidéo) peut couper une autre alerte en cours.

### Affichage d'une alerte sur le dashboard

Dès que `alerte_active` est vrai ou qu'une personne a été détectée il y a moins de 15 s, un **bandeau rouge** apparaît en haut de la page (sous le titre), avec un récapitulatif en une ligne par type d'alerte en cours (heure, valeurs, confiance). Il disparaît automatiquement au retour à la normale.

Chaque alerte capteurs, dans la liste du bas, a un bouton **Détail** qui affiche :
- une phrase qui nomme la caractéristique la plus responsable de l'anomalie (ex. « surtout causée par humidité : 76 contre 50 habituellement, soit 13 σ au-dessus ») ;
- le tableau complet des 5 caractéristiques (valeur, normal appris, écart en écarts-types) ;
- un mini-graphe température/gaz sur la fenêtre 10 min avant → 2 min après l'alerte, avec une ligne pointillée au moment exact.

Ce mini-graphe est construit côté navigateur à partir des mesures déjà chargées (limite 100, fenêtre d'une heure) : pour une alerte ancienne ou après un rechargement de page, il peut afficher « pas assez de mesures en mémoire » au lieu du graphe.

## 12. Surveillance vidéo

Une webcam branchée sur le PC serveur surveille la table. YOLOv8 nano détecte les objets image par image et renvoie le flux avec les détections dessinées.

Le module ne tourne **pas** dans Docker, car un conteneur Windows n'accède pas à la webcam USB. L'ESP32 n'intervient pas dans cette partie : tout passe par le PC serveur.

### Ce qui est détecté

| Détection | Affichage | Effet |
|---|---|---|
| **Personne** (`person`) | cadre rouge, avec la confiance | après 3 s de présence continue : événement, buzzer 10 s, mail |
| **Animal** (`bird`, `cat`, `dog`, `horse`, `sheep`, `cow`, `elephant`, `bear`, `zebra`, `giraffe`) | cadre orange | rien d'autre : ni alerte, ni buzzer, ni mail |
| Autre objet, ou confiance < 50 % | rien | rien |

### Déclenchement d'une personne

- Une personne doit rester visible **3 secondes** pour que l'événement soit envoyé. Un passage d'une seule image ne déclenche rien.
- Si elle disparaît pendant **2 secondes**, la règle se réarme : la prochaine présence donnera un nouvel événement.
- Un seul événement est envoyé par présence confirmée.
- Le dashboard affiche une barre de progression sur les 3 secondes. Elle passe en rouge avec « Confirmée : alerte envoyée ».

### Changer de webcam

Le module liste les webcams disponibles au démarrage (index 0 à 4). Le dashboard affiche un sélecteur « Caméra » s'il y en a plusieurs, et le changement se fait sans redémarrer. Une webcam branchée après le démarrage n'apparaît qu'après un redémarrage du module.

### Vérification rapide

- `http://localhost:8001/cameras` liste les caméras.
- `http://localhost:8001/stream` affiche le flux avec les cadres.
- Une personne devant la caméra : la barre se remplit, puis `GET /api/v1/detections` affiche une ligne et le buzzer s'active.

### Limites de la vidéo

- La détection tourne sur le processeur : la fréquence d'images dépend de la machine. Sur un portable Windows, on mesure environ 13 à 15 images par seconde (le sujet demande moins de 100 ms par image).
- Un éclairage faible, une personne de dos ou partiellement cachée peuvent ne pas être détectés.
- Aucune vidéo n'est enregistrée : seules la détection et la capture envoyée par mail existent.
- Le flux vidéo n'est pas authentifié et circule en clair sur le réseau de la table.

## 13. Alertes par mail

### Configuration

Les alertes sont envoyées via Gmail en SMTP, avec un **mot de passe d'application** (voir [configuration](#6-configuration)). Google n'accepte plus le mot de passe principal pour ce genre d'envoi.

Pour créer le mot de passe d'application :
1. Active la validation en deux étapes sur le compte Gmail.
2. Crée un mot de passe d'application sur https://myaccount.google.com/apppasswords.
3. Copie les 16 caractères, sans espaces, dans `GMAIL_APP_PASSWORD`.

Les comptes scolaires (Google Workspace) peuvent avoir cette option désactivée par l'administrateur : dans ce cas, utilise un compte Gmail dédié au projet.

### Contenu

| Événement | Objet | Contenu |
|---|---|---|
| Anomalie capteurs | `[SENTINEL-X] Anomalie capteurs · table1` | température, humidité, gaz, rappel que l'alarme sonore est activée |
| Hausse de température | `[SENTINEL-X] Hausse de température · table1` | température actuelle, probabilité de hausse du modèle avec barre |
| Personne détectée | `[SENTINEL-X] Personne détectée · table1` | confiance avec barre, capture annotée intégrée et jointe (`capture.jpg`), vidéo de 10 s jointe (`sentinel-clip.mp4`) si elle tient dans la limite |

Les mails sont en HTML, avec une version texte pour les clients qui ne l'affichent pas. La vidéo est écartée, et seule la capture reste jointe, si capture et vidéo dépassent ensemble 20 Mo.

### Règle d'envoi

**Au plus un mail toutes les 5 minutes par type d'alerte** : un mail de capteurs, un mail de hausse de température et un mail de personne ont chacun leur propre délai. Un événement pendant le délai de son type ne donne pas de mail, mais il reste dans la base et sur le dashboard. Au maximum, on peut donc recevoir trois mails dans une même fenêtre de 5 minutes. Le délai est en mémoire, il repart à zéro au redémarrage du backend.

Les envois se font dans un thread séparé : un mail lent ou en échec ne bloque ni MQTT, ni l'API.

## 14. Tests et CI/CD

### Tests

| Suite | Nombre | Contenu |
|---|---|---|
| `backend/tests` | 26 | modèle capteurs, hausse de température, API, détection, vision (enregistrement et buzzer), mails (cooldown par type, contenu, photo, vidéo) |
| `vision/tests` | 4 | règle de classement : personne, animal, autre objet, confiance faible |

Backend, en local (Python 3.12) :

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Dans l'image Docker (depuis PowerShell) :

```powershell
docker compose build backend
docker run --rm -v "${PWD}\backend:/code" -w /code workshop-backend sh -c "pip install -q -r requirements-dev.txt && pytest"
```

Vision :

```powershell
cd vision
.venv\Scripts\python.exe -m pip install pytest==8.3.4
.venv\Scripts\python.exe -m pytest
```

Les tests n'envoient aucun mail et n'utilisent ni webcam ni YOLO.

### Workflow GitHub Actions

Fichier `.github/workflows/ci.yml`, déclenché sur chaque push et pull request vers `main`.

| Job | Ce qu'il vérifie |
|---|---|
| `backend-tests` | `pytest` |
| `frontend-build` | `npm ci` puis `npm run build` |
| `stack-e2e` | démarre la stack, attend `/health`, publie une mesure MQTT et vérifie qu'elle arrive dans l'API, puis entraîne le modèle sur 120 mesures |
| `publish-image` | sur `main` seulement, si tout est vert : publie l'image backend sur GHCR (`ghcr.io/swaksm/sentinel-x-backend`, tags `latest` et `<sha>`) |

La CI ne couvre ni la vision (sauf la logique de classement hors CI), ni l'envoi réel de mails, ni le firmware.

## 15. Simulateur

Sans ESP32, `tools/simulate_sensors.py` publie des mesures normales toutes les 5 s. Avec `--pic`, il envoie un pic de gaz à 60 s.

Il tourne dans le conteneur backend, car paho-mqtt n'est pas installé sur l'hôte :

```bash
docker compose exec -T backend python - --host mosquitto --pic < tools/simulate_sensors.py
```

Options : `--table` (défaut `table1`), `--host` (défaut `localhost`), `--port` (défaut 1883), `--intervalle` (défaut 5 s), `--pic`.

Scénario de test :
1. Laisse tourner environ 2 minutes pour dépasser 100 mesures.
2. Entraîne le modèle : `POST /api/v1/tables/table1/entrainement`.
3. Attends le pic à 60 s, puis vérifie `GET /api/v1/tables/table1/etat` : `alerte_active` doit valoir `true`.

## 16. Limites connues

- **Buzzer partagé** : l'alerte capteurs et la détection vidéo utilisent le même buzzer. Une fin de buzzer déclenchée par l'une peut couper l'autre.
- **Fausse alerte capteurs après un pic** : pendant que le pic sort de la fenêtre de 30 mesures, la pente change et une mesure normale peut être signalée.
- **Délai de mail par type** : un événement du même type pendant les 5 minutes suivantes ne donne pas de mail.
- **Modèle de hausse simulé** : le Random Forest de température n'a été entraîné que sur des données simulées. Il doit être réentraîné sur de vraies mesures.
- **Quota Gmail** : un compte personnel est limité à environ 500 mails par jour.
- **Vidéo basse qualité** : les clips sont en 320×240, pour rester petits et sous la limite de 20 Mo. Ce n'est pas la qualité du flux affiché sur le dashboard.
- **Clips non nettoyés** : les fichiers dans `media/` ne sont jamais supprimés automatiquement.
- **État en mémoire** : alerte active, délai de mail et présence vidéo ne sont pas persistés.
- **1883 reste sans TLS** : volontaire (réseau Docker interne et boucle locale uniquement, jamais exposé au Wi-Fi), mais ça veut dire que backend et vision ne se parlent pas en chiffré entre eux — sans conséquence tant qu'ils restent sur la même machine.
- **API et flux vidéo sans authentification**, et le flux circule en clair sur le réseau.
- **Pas de migrations** : le schéma est créé par `create_all`. Un changement impose de supprimer le volume `pgdata`.
- **Pas de purge** des mesures.
- **Un seul modèle capteurs par table**, sans versionnage.
- **Firmware non testé sur le matériel réel** : `firmware/sentinel_temp/sentinel_temp.ino` lit les capteurs, publie en MQTT/TLS et pilote le buzzer et les deux écrans OLED, mais n'a pas encore tourné sur un vrai ESP32.
- **Vision hors CI** : le module ne tourne pas dans la CI, et la règle de classement est la seule partie testée automatiquement.
- **Frontend** : une seule table codée en dur (`table1`) dans `App.jsx`, affichée sous le nom « Sentinel G9 ». Pas encore de conteneur Docker pour le frontend.
- **Connexion sans sécurité réelle** : l'écran de connexion (`admin` / `admin`) est vérifié dans le navigateur. Il ne protège ni l'API ni le flux vidéo.

## 17. Feuille de route

1. Tester le firmware sur un vrai ESP32 (Wi-Fi labo, TLS, double OLED).
2. Authentification de l'API et du flux vidéo.
3. Migrations Alembic, purge des mesures.
4. Correction de la fausse alerte après un pic.
5. Buzzer distinct pour la vidéo et pour les capteurs.
6. Sélection de la table dans le frontend, conteneur Docker du frontend.
