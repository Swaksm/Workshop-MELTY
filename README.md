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
│   │   ├── detection.py     # évaluation d'une mesure, alerte capteurs, buzzer, mail
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
| `backend` | 8000 | API REST et Swagger |
| `mosquitto` | 1883 | broker MQTT |
| `db` | non exposé | PostgreSQL, réseau Docker uniquement |

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

Toute la communication se fait sur un réseau local créé par le PC serveur. Rien ne sort vers internet.

### Plan d'adressage

| Équipement | Adresse | Rôle |
|---|---|---|
| PC serveur (passerelle du hotspot) | `192.168.52.1` (à vérifier) | héberge Mosquitto (1883) et l'API (8000), crée le hotspot |
| ESP32 | `192.168.52.50` (IP fixe) | publie les mesures |
| Autres appareils | DHCP, `192.168.52.x` | consultent l'API depuis le navigateur |
| Masque | `255.255.255.0` (`/24`) | tous les appareils de la table |

Le plan ci-dessus est la cible du projet. **Windows peut attribuer une autre adresse au hotspot** (par défaut `192.168.137.1`). L'adresse réelle est celle que `ipconfig` affiche : le firmware doit la reprendre.

### Créer le hotspot

1. Paramètres → Réseau et Internet → **Point d'accès mobile**.
2. Nom : `Sentinel_G9`, mot de passe : `Sentinel_G9`.
3. Bande : **2,4 GHz** (l'ESP32 ne supporte pas la 5 GHz).
4. Active le point d'accès.

Certaines cartes Wi-Fi ne peuvent pas être connectées au Wi-Fi de l'école et diffuser le hotspot en même temps.

### Vérifier l'adresse du PC

```powershell
ipconfig
```

Cherche la carte « Connexion au réseau local* N » connectée, avec une IPv4 : c'est l'adresse du PC serveur sur le hotspot. Si elle affiche `Média déconnecté`, le hotspot n'est pas actif.

### Adapter le firmware

Trois valeurs dans le firmware, à remplacer par le préfixe réel. Exemple avec `192.168.137.1` :

| Variable | Valeur |
|---|---|
| `local_IP` | `192.168.137.50` |
| `gateway` | `192.168.137.1` |
| `MQTT_HOST` | `192.168.137.1` |

Le masque ne change pas.

### Ouvrir les ports (pare-feu Windows)

Une fois, dans un terminal **administrateur** :

```powershell
New-NetFirewallRule -DisplayName "SENTINEL-X MQTT" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "SENTINEL-X API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "SENTINEL-X Vision" -Direction Inbound -Protocol TCP -LocalPort 8001 -Action Allow -Profile Private
```

### Qui parle à qui

| De | Vers | Protocole et port | Usage |
|---|---|---|---|
| ESP32 `192.168.52.50` | PC `192.168.52.1:1883` | MQTT (TCP) | publie `sentinelx/table1/sensors` |
| Backend (conteneur) | `mosquitto:1883` | MQTT (réseau Docker) | reçoit capteurs et vision, envoie les commandes |
| Backend (conteneur) | `db:5432` | PostgreSQL (réseau Docker) | enregistre les données |
| Vision (PC) | `localhost:1883` | MQTT | publie `sentinelx/table1/vision` |
| Backend (conteneur) | `smtp.gmail.com:587` | SMTP (STARTTLS) | envoie les mails |
| Navigateur du PC | `localhost:8000`, `localhost:8001` | HTTP | API, Swagger, flux vidéo |
| Autre appareil | `192.168.52.1:8000` | HTTP | API et Swagger |

Le backend parle à Mosquitto et à la base par les **noms de service Docker**, pas par l'IP du PC.

### Vérifier que tout communique

```powershell
ipconfig
Test-NetConnection 192.168.52.1 -Port 1883
curl http://localhost:8000/health
```

### Problèmes courants

| Symptôme | Cause probable |
|---|---|
| Le hotspot ne démarre pas | la carte Wi-Fi partage déjà la connexion de l'école |
| L'ESP32 se connecte au Wi-Fi, mais `Connexion MQTT... échec` | mauvaise adresse du PC dans le firmware, ou pare-feu qui bloque 1883 |
| Les autres appareils n'atteignent pas l'API | pare-feu qui bloque 8000, ou profil réseau « Public » |

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
4. Au passage en anomalie : une ligne dans `alerts`, `buzzer on`, et un mail si le délai de 5 minutes est écoulé.
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
| ESP32 → backend | `sentinelx/<table>/sensors` | `{"temp":23.4,"hum":51.2,"gas":1234}` | toutes les 5 s |
| vision → backend | `sentinelx/<table>/vision` | `{"label":"person","confidence":0.91,"image":"<base64 JPEG>","clip":"clip_table1_...mp4"}` | une fois par présence confirmée, 5 s après la confirmation |
| backend → ESP32 | `sentinelx/<table>/cmd` | `{"buzzer":"on"}` ou `{"buzzer":"off"}` | sur événement |

- `temp` : °C, un chiffre après la virgule. `hum` : humidité relative en %. `gas` : valeur ADC brute, entier de 0 à 4095.
- Le champ `image` est facultatif. Un label autre que `person` est refusé.
- Le broker de développement accepte les connexions anonymes sur 1883 (voir [limites](#16-limites-connues)).

Test manuel :

```bash
mosquitto_sub -h localhost -t "sentinelx/#" -v
mosquitto_pub -h localhost -t "sentinelx/table1/cmd" -m '{"buzzer":"on"}'
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

### `alerts` : une ligne par passage en anomalie capteurs

| Colonne | Type | Contrainte | Description |
|---|---|---|---|
| `id` | `integer` | clé primaire, auto | identifiant |
| `table_id` | `varchar(64)` | non null, indexée | table |
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

**Algorithme.** Pipeline scikit-learn : `StandardScaler` puis `LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.05)`. Un point est une anomalie s'il se trouve dans une zone beaucoup moins dense que ses 20 voisins appris.

**Entraînement.** `POST /entrainement` lit jusqu'à 5000 mesures, calcule les 5 valeurs pour chacune, entraîne le pipeline et l'enregistre dans `backend/models/<table>.joblib`. Le réentraînement remplace le modèle précédent.

**Bonnes pratiques.** Entraîne sur une période normale : pas de test au gaz, pas de passage devant la caméra, pas de pic simulé. Ce qui est dans les données d'entraînement est appris comme normal.

**Choix du modèle.** Sur des données simulées, Isolation Forest détectait 94 % des pics avec 6,8 % de fausses alertes, et LOF détecte 100 % des pics avec 0,5 % de fausses alertes. Ces chiffres viennent de données simulées : à revérifier avec les vraies mesures.

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
| Personne détectée | `[SENTINEL-X] Personne détectée · table1` | confiance avec barre, capture annotée intégrée et jointe (`capture.jpg`), vidéo de 10 s jointe (`sentinel-clip.mp4`) si elle tient dans la limite |

Les mails sont en HTML, avec une version texte pour les clients qui ne l'affichent pas. La vidéo est écartée, et seule la capture reste jointe, si capture et vidéo dépassent ensemble 20 Mo.

### Règle d'envoi

**Au plus un mail toutes les 5 minutes**, tous événements confondus. Un événement pendant ce délai ne donne pas de mail : il reste dans la base et sur le dashboard. Le délai est en mémoire, il repart à zéro au redémarrage du backend.

Les envois se font dans un thread séparé : un mail lent ou en échec ne bloque ni MQTT, ni l'API.

## 14. Tests et CI/CD

### Tests

| Suite | Nombre | Contenu |
|---|---|---|
| `backend/tests` | 21 | modèle capteurs, API, détection, vision (enregistrement et buzzer), mails (cooldown, contenu, photo, vidéo) |
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
- **Délai de mail global** : un événement pendant les 5 minutes suivantes ne donne pas de mail, même si c'est un événement différent.
- **Quota Gmail** : un compte personnel est limité à environ 500 mails par jour.
- **Vidéo basse qualité** : les clips sont en 320×240, pour rester petits et sous la limite de 20 Mo. Ce n'est pas la qualité du flux affiché sur le dashboard.
- **Clips non nettoyés** : les fichiers dans `media/` ne sont jamais supprimés automatiquement.
- **État en mémoire** : alerte active, délai de mail et présence vidéo ne sont pas persistés.
- **MQTT en clair, sans authentification** : Mosquitto accepte les connexions anonymes sur 1883. Le sujet exige MQTTS et des identifiants.
- **API et flux vidéo sans authentification**, et le flux circule en clair sur le réseau.
- **Pas de migrations** : le schéma est créé par `create_all`. Un changement impose de supprimer le volume `pgdata`.
- **Pas de purge** des mesures.
- **Un seul modèle capteurs par table**, sans versionnage.
- **Firmware incomplet** : le firmware de `firmware/` ne fait que le Wi-Fi en IP fixe et l'OTA. La lecture du DHT22 et la publication MQTT sont dans un autre croquis, non committé.
- **Vision hors CI** : le module ne tourne pas dans la CI, et la règle de classement est la seule partie testée automatiquement.
- **Frontend** : une seule table codée en dur (`table1`) dans `App.jsx`. Pas encore de conteneur Docker pour le frontend.

## 17. Feuille de route

1. Firmware complet : lecture du DHT22 et du MQ-2, publication MQTT, abonnement au buzzer.
2. TLS sur MQTT, authentification du broker, authentification de l'API.
3. Migrations Alembic, purge des mesures.
4. Correction de la fausse alerte après un pic.
5. Buzzer distinct pour la vidéo et pour les capteurs.
6. Sélection de la table dans le frontend, conteneur Docker du frontend.
