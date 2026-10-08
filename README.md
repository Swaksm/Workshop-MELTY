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
16. [Supervision et rétention (MCO)](#16-supervision-et-rétention-mco)
17. [Limites connues](#17-limites-connues)
18. [Feuille de route](#18-feuille-de-route)

## 1. Architecture

```
                         ┌─────────── PC serveur (Wi-Fi école, ex. 10.0.3.173) ──────────────┐
ESP32 (Wi-Fi école)      │                                                                   │
 DHT22 · MQ-2 · PIR      │  Docker Compose (réseau interne 172.18.0.0/16)                    │
 OLED · buzzer           │   ┌───────────┐   ┌──────────┐   ┌────────────┐   ┌──────────┐    │
        │                │   │ mosquitto │◄──┤ backend  │──►│ PostgreSQL │   │ cAdvisor │    │
        │ MQTT/TLS 8883  │   │ 1883 int. │──►│ FastAPI  │   │   :5432    │   │  :8080   │    │
        └───────────────►│   │ 8883 TLS  │   │  :8000   │   └────────────┘   └──────────┘    │
                         │   └───────────┘   └────┬─────┘                                    │
Webcam USB (PC)          │        ▲ MQTT 1883     │ SMTP (Gmail)                             │
   │                     │        │ (127.0.0.1)   ▼                                          │
   ▼                     │   ┌────┴───────────┐  Boîte mail de l'équipe                      │
 vision/app.py ──────────┼──►│ vision (hors   │                                              │
 YOLOv8 nano · :8001     │   │ Docker, sur PC)│                                              │
                         │   └────────────────┘                                              │
                         └───────────────────────────────────────────────────────────────────┘
                                         ▲                    ▲
      navigateur ──HTTPS :443──► proxy Caddy (conteneur) ─┬─ /api/*    → backend :8000
      (PC ou autre poste)                                 ├─ /vision/* → vision :8001 (si session valide)
                                                          └─ /         → dashboard React compilé
```


- Les **capteurs** passent par MQTT, puis le backend les enregistre et évalue le modèle d'IA.
- La **vidéo** passe par le module vision, qui tourne sur le PC et non dans Docker : un conteneur Windows n'accède pas à la webcam USB.
- Les **alertes** déclenchent le buzzer et, au plus une fois toutes les 5 minutes, un mail.
- Depuis le Wi-Fi, seuls deux ports sont joignables, tous deux chiffrés : MQTT/TLS (8883) pour l'ESP32 et HTTPS (443) pour le dashboard, l'API et la vidéo. Le HTTPS n'est accessible qu'aux 5 postes autorisés (certificat client), puis exige une connexion. Réseau : [docs/reseau.md](docs/reseau.md). Sécurité (matrice menace → mesure → preuve) : [docs/securite.md](docs/securite.md).

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
| Infra | Docker Compose, Caddy (reverse proxy HTTPS), cAdvisor (supervision) |

## 3. Structure du dépôt

```
.
├── backend/
│   ├── app/
│   │   ├── main.py          # routes FastAPI et cycle de vie (MQTT, tables)
│   │   ├── auth.py          # connexion, jeton JWT (cookie HttpOnly ou Bearer), anti-force brute
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
│   │   ├── retention.py     # purge horaire des vieilles mesures et des vieux clips
│   │   ├── supervision.py   # état de la machine : CPU/RAM, base, clips, broker MQTT
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
│   ├── vite.config.js       # dev : proxy /api → :8000 et /vision → :8001
│   └── Dockerfile           # compile le dashboard et l'embarque dans l'image Caddy
├── proxy/
│   └── Caddyfile            # reverse proxy HTTPS : dashboard, /api, /vision (session vérifiée)
├── firmware/
│   └── sentinel_wifi/sentinel_wifi.ino  # connexion WiFi en IP fixe, OTA
├── mosquitto/
│   ├── mosquitto.conf       # configuration du broker (1883 interne, 8883 TLS)
│   ├── acl                  # droits de chaque compte MQTT
│   └── gen-certs.sh         # CA (une fois) et certificat du broker pour l'IP du PC
├── docs/
│   ├── reseau.md            # réseau : schéma, plan d'adressage, flux, isolation
│   └── securite.md          # matrice de sécurité, protocole de preuves
├── tools/
│   ├── simulate_sensors.py  # publie de fausses mesures sur le broker
│   └── supervision.ps1      # état de la machine : conteneurs, logs, volumes
├── media/                   # clips vidéo des détections (ignoré par Git, créé au premier clip)
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
└── README.md
```

## 4. Installation et lancement

### Lancement rapide (Windows)

Une seule commande démarre tout : Docker Desktop si besoin, la stack (base, broker, backend, proxy HTTPS, supervision), le dashboard de développement et le module vision.

```powershell
powershell -ExecutionPolicy Bypass -File .\lancer.ps1
```

Options : `-CameraIndex 1` pour une autre webcam, `-SansVision` ou `-SansFront` pour ne pas lancer une partie, `-ForcerIp 10.0.3.42` si la détection de l'adresse Wi-Fi se trompe.

Ensuite :

- dashboard : **https://&lt;IP du PC&gt;** (ou https://localhost sur le PC serveur), **réservé aux postes autorisés** : chaque poste doit avoir importé son certificat (voir ci-dessous). Identifiant `admin`, mot de passe `ADMIN_PASSWORD` du fichier `.env` (généré au premier lancement) ;
- dashboard de développement (rechargement à chaud) : http://localhost:5173, sur le PC serveur uniquement.

### Autoriser un poste à ouvrir le dashboard

Au premier lancement, `lancer.ps1` crée 5 certificats de poste (`NB_CLIENTS` dans le `.env`) dans `mosquitto\certs\clients\` : `poste1.p12` à `poste5.p12`, chacun avec son mot de passe dans `posteN.mot-de-passe.txt`. Le proxy HTTPS n'accepte que ces postes : sans certificat, le navigateur affiche `ERR_BAD_SSL_CLIENT_AUTH_CERT`, même pas la page de connexion.

Pour chaque personne autorisée :

1. lui remettre **son** `posteN.p12` et `ca.crt` (clé USB), et le mot de passe séparément. **Jamais `ca.key`** ;
2. sur son PC, dans PowerShell, dans le dossier des fichiers :
   ```powershell
   Import-PfxCertificate -FilePath .\posteN.p12 -CertStoreLocation Cert:\CurrentUser\My -Password (Read-Host -AsSecureString "Mot de passe")
   Import-Certificate -FilePath .\ca.crt -CertStoreLocation Cert:\CurrentUser\Root
   ```
   (ou double-clic sur le `.p12` : « Utilisateur actuel », mot de passe, magasin automatique) ;
3. fermer et rouvrir le navigateur, ouvrir `https://<IP du PC>` et choisir le certificat « Sentinel-X posteN » quand le navigateur le propose.

Une fois distribués, `posteN.p12`, `posteN.key` et `posteN.mot-de-passe.txt` peuvent être supprimés du serveur : seul `posteN.crt` doit y rester. **Révoquer un poste** : supprimer `posteN.crt` puis relancer `lancer.ps1` ; un nouveau certificat est créé et l'ancien est refusé. Les certificats des postes ne changent pas quand l'IP du PC change.

À chaque lancement, le script reconstruit les images si le code a changé (après un `git pull`, le backend est donc toujours à jour), détecte l'adresse du PC sur le Wi-Fi, (re)génère le certificat TLS (broker et proxy HTTPS) si elle a changé et redémarre les services concernés, et met à jour `MQTT_HOST` et `ca_cert.h` pour le firmware (voir [Réseau de la table](#5-réseau-de-la-table)).

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
| `proxy` | 443 | Caddy : HTTPS avec certificat client exigé (postes autorisés), dashboard compilé, `/api` et `/vision`, sur `127.0.0.1` et `SERVER_IP` |
| `backend` | 8000 | API REST et Swagger, sur `127.0.0.1` uniquement (depuis le Wi-Fi : `https://<IP>/api`) |
| `mosquitto` | 1883 et 8883 | broker MQTT : 1883 en clair sur `127.0.0.1` (backend, vision), 8883 en TLS sur `127.0.0.1` et `SERVER_IP` (ESP32) |
| `db` | non exposé | PostgreSQL, réseau Docker uniquement |
| `cadvisor` | 8080 | supervision CPU/RAM par conteneur, sur `127.0.0.1` uniquement |

Les conteneurs tournent sous un utilisateur non-root, sans privilèges supplémentaires et avec système de fichiers en lecture seule (sauf les volumes de données). En lancement manuel, `SERVER_IP` doit être renseignée dans le `.env` (adresse Wi-Fi du PC, ou `127.0.0.2` en local) : sans elle, `docker compose` refuse de démarrer plutôt que d'ouvrir les ports sur toutes les interfaces. Les certificats se créent avec `sh mosquitto/gen-certs.sh <IP du PC>`.

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

Le PC serveur et l'ESP32 sont sur le **Wi-Fi de l'école**. Deux flux seulement traversent ce Wi-Fi partagé, tous deux chiffrés : le MQTT de l'ESP32 (TLS, 8883) et le HTTPS du dashboard (443). Tout le reste (vision, base, supervision, API directe) reste sur le PC.

Le dossier complet est dans **[docs/reseau.md](docs/reseau.md)** : schéma, plan d'adressage, ports exposés, matrice des flux autorisés, isolation vis-à-vis des autres groupes, et l'amélioration prévue (réseau privé dédié `192.168.10.0/24`).

### Plan d'adressage

| Équipement | Adresse | Rôle |
|---|---|---|
| PC serveur | DHCP de l'école (ex. `10.0.3.173/24`, passerelle `10.0.3.1`) | Mosquitto (8883 TLS), proxy HTTPS (443) |
| ESP32 | DHCP de l'école | publie les mesures en TLS |
| Conteneurs | réseau Docker interne `172.18.0.0/16` | joignables par leur nom de service uniquement |

### Quand l'adresse du PC change

Le DHCP de l'école peut donner une autre adresse d'un jour à l'autre. `lancer.ps1` s'en occupe :

1. il détecte l'adresse de la carte Wi-Fi physique connectée (celle qui a une passerelle) et l'écrit dans `SERVER_IP` du `.env` ;
2. si le certificat du broker ne correspond pas à cette adresse, il en signe un nouveau. **La CA ne change pas**, donc l'ESP32 n'a pas besoin d'un nouveau certificat ;
3. il met à jour `MQTT_HOST` dans `firmware/sentinel_temp/secrets.h` (s'il existe) et régénère `ca_cert.h`, puis affiche « IP changée » : il reste à **reflasher l'ESP32** (câble ou OTA).

### Se connecter au Wi-Fi de l'école

Le SSID et le mot de passe vont dans `firmware/sentinel_temp/secrets.h` (`WIFI_SSID`, `WIFI_PASSWORD`), jamais dans le dépôt. Copier `secrets.h.example` en `secrets.h` la première fois.

### Chiffrement TLS du MQTT

| Port | Chiffrement | Qui l'utilise |
|---|---|---|
| 1883 | aucun | backend (`mosquitto:1883`, réseau Docker) et module vision (`127.0.0.1:1883`). Jamais exposé sur le Wi-Fi |
| 8883 | TLS 1.2 minimum | ESP32, seul client qui traverse le Wi-Fi |

Les certificats sont dans `mosquitto/certs/` et ne sont jamais commités : `ca.crt`/`ca.key` (autorité de certification, créée une seule fois, 2 ans) et `server.crt`/`server.key` (certificat du broker, IP du PC dans le CN et le SAN, 1 an). `lancer.ps1` les crée tout seul. À la main : `sh mosquitto/gen-certs.sh <IP du PC>`.

`lancer.ps1` recrée aussi `mosquitto/passwd` à chaque lancement à partir des mots de passe du `.env` (`MQTT_PASSWORD`, `VISION_MQTT_PASSWORD`, `ESP32_MQTT_PASSWORD`).

### Ouvrir les ports (pare-feu Windows)

En général rien à faire : la règle de pare-feu installée par Docker Desktop laisse passer les ports qu'il publie. Si l'ESP32 ou les autres postes restent bloqués (le Wi-Fi de l'école est en profil **Public**, à vérifier avec `Get-NetConnectionProfile`), ouvrir les deux ports une fois, dans un terminal **administrateur** :

```powershell
New-NetFirewallRule -DisplayName "SENTINEL-X MQTT TLS" -Direction Inbound -Protocol TCP -LocalPort 8883 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "SENTINEL-X HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -Profile Any
```

### Qui parle à qui

| De | Vers | Protocole et port | Usage |
|---|---|---|---|
| ESP32 | PC `SERVER_IP:8883` | MQTT sur TLS | publie `sentinelx/table1/sensors`, authentifié (`esp32`) |
| Backend (conteneur) | `mosquitto:1883` | MQTT en clair (réseau Docker) | reçoit capteurs, vision et statistiques `$SYS`, envoie les commandes |
| Backend (conteneur) | `db:5432` | PostgreSQL (réseau Docker) | enregistre les données |
| Vision (PC) | `localhost:1883` | MQTT en clair (boucle locale) | publie `sentinelx/table1/vision` |
| Backend (conteneur) | `smtp.gmail.com:587` | SMTP (STARTTLS) | envoie les mails |
| Navigateur (PC ou autre poste) | `SERVER_IP:443` | HTTPS | dashboard, API (`/api`), flux vidéo (`/vision`), connexion requise |
| Proxy Caddy (conteneur) | `backend:8000`, `host.docker.internal:8001` | HTTP interne au PC | relaie l'API et le flux vidéo |
| Navigateur du PC | `localhost:5173`, `:8000`, `:8080` | HTTP local | dashboard de dev, Swagger, cAdvisor |

Le backend parle à Mosquitto et à la base par les **noms de service Docker**, pas par l'IP du PC.

### Vérifier que tout communique

```powershell
ipconfig
docker compose ps
Test-NetConnection <IP du PC> -Port 8883
openssl s_client -connect <IP du PC>:8883 -CAfile mosquitto/certs/ca.crt -verify_ip <IP du PC> -brief
curl http://localhost:8000/health
```

### Problèmes courants

| Symptôme | Cause probable |
|---|---|
| L'ESP32 se connecte au Wi-Fi, mais `Connexion MQTT... échec` | l'IP du PC a changé et l'ESP32 n'a pas été reflashé, pare-feu qui bloque 8883 (profil Public), ou mot de passe `esp32` / `ca_cert.h` obsolètes |
| `lancer.ps1` annonce `Wi-Fi inactif` | pas de carte Wi-Fi connectée avec une passerelle : se connecter au Wi-Fi, ou forcer avec `-ForcerIp` |
| `docker compose up` : `SERVER_IP` manquante | lancement manuel sans `SERVER_IP` dans le `.env` : lancer `lancer.ps1` ou renseigner la variable |
| Les autres postes n'atteignent pas le dashboard | pare-feu qui bloque 443 (voir « Ouvrir les ports »), ou mauvaise adresse : utiliser `https://<IP du PC>` |
| `ERR_BAD_SSL_CLIENT_AUTH_CERT` dans le navigateur | ce poste n'a pas de certificat autorisé, ou il a été révoqué : importer son `posteN.p12` (voir « Autoriser un poste »), puis rouvrir le navigateur |
| Le navigateur ne propose aucun certificat | le `.p12` n'est pas dans le magasin « Personnel » de l'utilisateur Windows, ou le navigateur n'a pas été redémarré (Firefox a son propre magasin : Paramètres, Certificats, Vos certificats, Importer) |
| Avertissement `NET::ERR_CERT_AUTHORITY_INVALID` dans le navigateur | la CA n'est pas importée sur ce poste : `Import-Certificate` (voir « Autoriser un poste ») avec le `ca.crt` du PC qui fait tourner la stack |
| Avertissement `NET::ERR_CERT_COMMON_NAME_INVALID` | certificat d'une ancienne IP encore en mémoire : relancer `lancer.ps1`, ou `docker compose restart proxy mosquitto` |
| « Not Found » en se connectant au dashboard | backend resté à une ancienne version (image construite avant un `git pull`) : relancer `lancer.ps1`, qui reconstruit maintenant toujours les images |
| Le dashboard revient à l'écran de connexion | le jeton a expiré (8 h) ou le backend a été recréé avec un autre `JWT_SECRET` : se reconnecter |
| `lancer.ps1` échoue avec « Docker ne répond pas » | Docker Desktop bloqué sur un ancien socket (`%LOCALAPPDATA%\Docker\run`). Redémarre Windows : le verrou disparaît. Ne pas réinitialiser Docker en usine, ça efface les volumes |
| Le backend ne peut pas écrire les modèles (`Permission denied` sur `/code/models`) | le volume `model-data` appartient à root. Le corriger sans rien supprimer : `docker run --rm -v sentinelx_model-data:/m alpine chown -R 10001:10001 /m` |
| Le module vision ne voit pas une webcam branchée | il ne scanne les caméras qu'au démarrage : relance `lancer.ps1` (ou `arreter.ps1` puis `lancer.ps1`) |
| Mosquitto refuse de démarrer, erreur sur `cafile` | `mosquitto/certs/` absent : relance `lancer.ps1`, ou `sh mosquitto/gen-certs.sh <IP du PC>` |

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
| `SERVER_IP` | `10.0.3.173` | `docker compose` | adresse du PC sur le Wi-Fi, où l'ESP32 joint le broker et l'API. Mise à jour automatiquement par `lancer.ps1` (`127.0.0.2` si le Wi-Fi est coupé). Obligatoire |
| `GMAIL_USER` | `adresse@gmail.com` | `backend` | compte qui envoie les mails |
| `GMAIL_APP_PASSWORD` | `abcdefghijklmnop` | `backend` | mot de passe d'application Google (16 caractères, sans espaces) |
| `ALERT_TO` | `equipe@exemple.com` | `backend` | destinataire des alertes |
| `MEDIA_DIR` | `media` | `backend` | dossier des clips vidéo, partagé avec le module vision |
| `RETENTION_MESURES_JOURS` | `7` | `backend` | mesures plus anciennes purgées (toutes les heures) |
| `RETENTION_CLIPS_JOURS` | `3` | `backend` | clips vidéo plus anciens supprimés |
| `MEDIA_MAX_MO` | `500` | `backend` | taille maximale du dossier des clips, les plus anciens partent en premier |
| `ADMIN_USER` | `admin` | `backend` | identifiant de connexion au dashboard et à l'API |
| `ADMIN_PASSWORD` | (généré) | `backend` | mot de passe de connexion, 24 caractères aléatoires générés par `lancer.ps1`. Vide : personne ne peut se connecter |
| `JWT_SECRET` | (généré) | `backend` | clé de signature des jetons. La changer déconnecte tout le monde |
| `JWT_DUREE_HEURES` | `8` | `backend` | durée de validité d'une session |
| `NB_CLIENTS` | `5` | `lancer.ps1` | nombre de postes autorisés à ouvrir le dashboard (un certificat client par poste) |

Si `GMAIL_USER`, `GMAIL_APP_PASSWORD` ou `ALERT_TO` manque, les mails sont désactivés sans erreur : les alertes restent dans la base, le buzzer fonctionne toujours.

Variables du module vision (lues par `vision/app.py`) :

| Variable | Défaut | Rôle |
|---|---|---|
| `CAMERA_INDEX` | `0` | webcam de départ (on peut changer depuis le dashboard) |
| `MQTT_HOST` | `localhost` | broker MQTT |
| `MQTT_PORT` | `1883` | port MQTT |
| `TABLE_ID` | `table1` | table à laquelle rattacher les détections |
| `STREAM_PORT` | `8001` | port de l'API et du flux vidéo |
| `STREAM_HOST` | `127.0.0.1` | adresse d'écoute ; depuis le réseau, le flux passe par le proxy HTTPS |
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

Une table à 1 mesure toutes les 5 s produit environ 17 000 lignes par jour dans `measurements`. Les mesures de plus de 7 jours sont purgées toutes les heures (voir [Supervision et rétention](#16-supervision-et-rétention-mco)), soit environ 120 000 lignes au maximum par table. Les alertes et les détections ne sont pas purgées : quelques lignes par jour, et elles servent d'historique de sécurité.

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

Base : `https://<IP du PC>/api/v1` (via le proxy), ou `http://localhost:8000/api/v1` sur le PC. Swagger n'est servi qu'en local.

### Authentification

Toutes les routes `/api/v1` exigent un jeton, sauf la connexion. `POST /api/v1/auth/login` avec `{"utilisateur": "admin", "mot_de_passe": "..."}` renvoie un jeton JWT (valable 8 h) et le pose dans un cookie `sentinelx_token` (HttpOnly, Secure, SameSite=Strict) : le navigateur l'envoie tout seul. Un script l'envoie dans l'en-tête `Authorization: Bearer <jeton>`. Après 10 échecs en une minute, la connexion est refusée (429) pendant une minute.

### Routes

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | état du service (public) |
| POST | `/api/v1/auth/login` | connexion : jeton dans la réponse et dans un cookie (public) |
| POST | `/api/v1/auth/logout` | efface le cookie de session |
| GET | `/api/v1/auth/verifier` | 204 si la session est valide, 401 sinon (utilisée par le proxy pour le flux vidéo) |
| GET | `/api/v1/mesures?table_id=&limit=` | dernières mesures, plus récentes d'abord (limit max 1000, défaut 100) |
| GET | `/api/v1/alertes?table_id=&limit=` | alertes capteurs (limit max 500, défaut 50) |
| GET | `/api/v1/detections?table_id=&limit=` | personnes détectées (limit max 500, défaut 50) |
| GET | `/api/v1/tables/{table_id}/etat` | `{"alerte_active": bool, "modele_entraine": bool}` |
| POST | `/api/v1/tables/{table_id}/entrainement` | entraîne le modèle capteurs (100 mesures minimum, 5000 au maximum) |
| POST | `/api/v1/tables/{table_id}/commande` | corps `{"buzzer":"on"}` ou `{"buzzer":"off"}`, renvoie 202 |
| GET | `/api/v1/supervision` | état de la machine : CPU/RAM/disque de l'hôte Docker, taille de la base, clips, statistiques du broker, dernière purge |

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
| `401` | jeton absent, expiré ou invalide ; mauvais identifiants |
| `429` | trop d'échecs de connexion |
| `422` | corps ou paramètres invalides |
| `500` | erreur interne, voir les logs du backend |

### Exemples

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
     -H "Content-Type: application/json" \
     -d '{"utilisateur":"admin","mot_de_passe":"<ADMIN_PASSWORD>"}' | python -c "import sys,json;print(json.load(sys.stdin)['token'])")
curl -H "Authorization: Bearer $TOKEN" "http://localhost:8000/api/v1/mesures?table_id=table1&limit=5"
curl -H "Authorization: Bearer $TOKEN" -X POST http://localhost:8000/api/v1/tables/table1/entrainement
curl -H "Authorization: Bearer $TOKEN" -X POST http://localhost:8000/api/v1/tables/table1/commande \
     -H "Content-Type: application/json" -d '{"buzzer":"on"}'
```

### API du module vision (port 8001)

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/stream` | flux MJPEG avec les cadres dessinés |
| GET | `/cameras` | `{"disponibles": [0, 1], "active": 0}` |
| POST | `/camera` | corps `{"index": 1}` : change de webcam sans redémarrer |
| GET | `/presence` | `{"progression": 0.66, "confirmee": false}` : avancement vers les 3 secondes |

Le module vision n'écoute que sur `127.0.0.1`. Depuis le réseau, il est joignable par `https://<IP du PC>/vision/...` : le proxy demande d'abord au backend si la session est valide (401 sinon).

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
curl -H "Authorization: Bearer $TOKEN" -X POST http://localhost:8000/api/v1/tables/table1/entrainement
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
- Sur le PC lui-même, `http://localhost:8001` reste sans authentification (depuis le réseau, le flux passe par le proxy HTTPS, qui exige une session).

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
| Anomalie capteurs | `[SENTINEL-X] Anomalie capteurs · table1` | température, humidité, gaz, phrase causale (caractéristique la plus responsable), tableau des 5 caractéristiques avec écarts, rappel que l'alarme sonore est activée |
| Hausse de température | `[SENTINEL-X] Hausse de température · table1` | température actuelle, probabilité de hausse avec barre, tableau des caractéristiques du modèle |
| Personne détectée | `[SENTINEL-X] Personne détectée · table1` | confiance avec barre, capture annotée intégrée et jointe (`capture.jpg`), vidéo de 10 s jointe (`sentinel-clip.mp4`) si elle tient dans la limite |

Les mails sont en HTML, avec une version texte pour les clients qui ne l'affichent pas. La vidéo est écartée, et seule la capture reste jointe, si capture et vidéo dépassent ensemble 20 Mo.

### Règle d'envoi

**Au plus un mail toutes les 5 minutes par type d'alerte** : un mail de capteurs, un mail de hausse de température et un mail de personne ont chacun leur propre délai. Un événement pendant le délai de son type ne donne pas de mail, mais il reste dans la base et sur le dashboard. Au maximum, on peut donc recevoir trois mails dans une même fenêtre de 5 minutes. Le délai est en mémoire, il repart à zéro au redémarrage du backend.

Les envois se font dans un thread séparé : un mail lent ou en échec ne bloque ni MQTT, ni l'API.

## 14. Tests et CI/CD

### Tests

| Suite | Nombre | Contenu |
|---|---|---|
| `backend/tests` | 52 | modèle capteurs, hausse de température, API, détection, vision (enregistrement et buzzer), mails (cooldown par type, contenu, photo, vidéo, détail/phrase causale), rétention (purge des mesures et des clips), supervision, authentification (jeton, cookie, 401, anti-force brute) |
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
docker run --rm -v "${PWD}\backend:/code" -w /code sentinelx-backend sh -c "pip install -q -r requirements-dev.txt && pytest"
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

## 16. Supervision et rétention (MCO)

Le maintien en condition opérationnelle (MCO) consiste à vérifier que la machine tient la charge dans la durée : messages MQTT en continu, base qui grossit, logs, clips vidéo.

### Ce qui est surveillé

| Outil | Où | Ce qu'il montre |
|---|---|---|
| Panneau « Supervision machine » | dashboard, rafraîchi toutes les 10 s | CPU, RAM et disque de l'hôte Docker, nombre et taille des mesures, taille de la base, clips, clients et messages MQTT par minute, règles de rétention |
| `GET /api/v1/supervision` | API | les mêmes données en JSON |
| cAdvisor | http://localhost:8080 (PC uniquement) | CPU, RAM, réseau et disque **par conteneur**, avec historique |
| `tools/supervision.ps1` | terminal | `docker stats`, taille des logs de chaque conteneur (dont Mosquitto), taille des volumes, résumé de l'API |

Les statistiques du broker viennent des topics `$SYS/broker/...` publiés par Mosquitto (le compte `backend` a le droit de les lire). Sous Docker Desktop, l'« hôte » vu par le backend est la machine virtuelle WSL2 qui fait tourner Docker.

cAdvisor lit les conteneurs via le socket containerd (Docker Desktop range ses conteneurs dans l'espace containerd `moby`), monté en lecture seule. Son interface n'est publiée que sur `127.0.0.1`.

### Ce qui est borné

| Donnée | Limite | Mécanisme |
|---|---|---|
| Logs de chaque conteneur, dont Mosquitto | 3 fichiers de 10 Mo, soit 30 Mo maximum | rotation Docker (`logging` dans `docker-compose.yml`) |
| Mesures en base | 7 jours | purge toutes les heures par le backend (`app/retention.py`) |
| Clips vidéo (`media/`) | 3 jours et 500 Mo | même purge : les clips trop vieux, puis les plus anciens tant que le dossier dépasse la taille maximale |
| Mémoire des conteneurs | `mem_limit` par service | Docker |

La purge tourne au démarrage du backend puis toutes les heures. Les durées se règlent dans le `.env` (section 6). PostgreSQL réutilise l'espace libéré (autovacuum) : la base ne rétrécit pas sur le disque, mais elle cesse de grossir.

## 17. Limites connues

- **Buzzer partagé** : l'alerte capteurs et la détection vidéo utilisent le même buzzer. Une fin de buzzer déclenchée par l'une peut couper l'autre.
- **Fausse alerte capteurs après un pic** : pendant que le pic sort de la fenêtre de 30 mesures, la pente change et une mesure normale peut être signalée.
- **Délai de mail par type** : un événement du même type pendant les 5 minutes suivantes ne donne pas de mail.
- **Modèle de hausse simulé** : le Random Forest de température n'a été entraîné que sur des données simulées. Il doit être réentraîné sur de vraies mesures.
- **Quota Gmail** : un compte personnel est limité à environ 500 mails par jour.
- **Vidéo basse qualité** : les clips sont en 320×240, pour rester petits et sous la limite de 20 Mo. Ce n'est pas la qualité du flux affiché sur le dashboard.
- **État en mémoire** : alerte active, délai de mail et présence vidéo ne sont pas persistés.
- **1883 reste sans TLS** : volontaire (réseau Docker interne et boucle locale uniquement, jamais exposé au Wi-Fi), mais ça veut dire que backend et vision ne se parlent pas en chiffré entre eux — sans conséquence tant qu'ils restent sur la même machine.
- **Un seul compte** (`admin`) partagé par l'équipe, sans rôles. Derrière Docker Desktop, tous les clients arrivent avec la même adresse : la limite d'échecs de connexion est commune à tous (fenêtre d'une minute).
- **CA privée et certificats de poste** : chaque poste autorisé doit importer `ca.crt` et son `posteN.p12`. Pas de liste de révocation : on révoque un poste en supprimant son certificat sur le serveur puis en relançant.
- **Pas de migrations** : le schéma est créé par `create_all`. Un changement impose de supprimer le volume `pgdata`.
- **Un seul modèle capteurs par table**, sans versionnage.
- **Réseau partagé avec les autres groupes** : le Wi-Fi de l'école n'isole pas la table. TLS, authentification et ACL protègent les données, mais pas contre un déni de service. L'adresse du PC change avec le DHCP, ce qui impose de reflasher l'ESP32 (voir [docs/reseau.md](docs/reseau.md)).
- **cAdvisor et le socket containerd** : cAdvisor a besoin de ce socket, qui donne la main sur les conteneurs. Il est monté en lecture seule et l'interface n'est publiée qu'en local.
- **Vision hors CI** : le module ne tourne pas dans la CI, et la règle de classement est la seule partie testée automatiquement.
- **Frontend** : une seule table codée en dur (`table1`) dans `App.jsx`, affichée sous le nom « Sentinel G9 ». Le dashboard compilé est servi par le proxy Caddy (`https://localhost`).
- **Certificat TLS régénéré à chaque lancement** : `gen-certs.sh` recrée un certificat serveur à chaque fois que l'IP détectée change (et parfois même sans changement selon la validité restante). Chaque régénération impose de reflasher l'ESP32 avec la nouvelle CA (`firmware/sentinel_temp/ca_cert.h`), sans quoi il ne se reconnecte plus en TLS. Pas de mécanisme pour éviter la régénération quand l'IP est stable.
- **Webcam débranchée pendant que la table tourne** : une caméra branchée après le démarrage est détectée automatiquement (re-sondage toutes les 5 s). En revanche, si la caméra **active** est débranchée, le module retente de l'ouvrir indéfiniment sans jamais basculer sur une autre caméra disponible : il faut la rebrancher ou changer de caméra à la main dans le dashboard.
- **Pas de reconnexion MQTT visible** : si le broker tombe, le backend et le module vision utilisent la reconnexion automatique de paho-mqtt, mais rien ne le signale sur le dashboard.
- **Clips vidéo** : le nom du clip n'est en base que depuis l'ajout de la colonne `detections.clip` (octobre 2026). Les détections enregistrées avant n'ont pas de bouton vidéo, même si le fichier existe encore sur disque. L'encodage H.264 (`avc1`) dépend du greffon FFmpeg de la machine : sur certains postes, OpenCV affiche un avertissement `Failed to load OpenH264 library` au démarrage du clip mais retombe sur un autre encodeur H.264 qui fonctionne quand même — à vérifier si l'avertissement devient une vraie erreur sur une autre machine.

## 18. Feuille de route

1. Éviter de régénérer le certificat TLS quand l'IP n'a pas changé (évite de reflasher l'ESP32 à chaque lancement).
2. Basculer automatiquement sur une autre caméra si la caméra active est débranchée.
3. Comptes nominatifs et rôles (lecture seule / commande) pour l'API.
4. Migrations Alembic.
5. Correction de la fausse alerte après un pic.
6. Buzzer distinct pour la vidéo et pour les capteurs.
7. Sélection de la table dans le frontend.
7. Réseau privé dédié à la table (`192.168.10.0/24`, point d'accès propre, ESP32 en IP fixe) : isolation réelle et fin des reflashs liés au DHCP de l'école.
