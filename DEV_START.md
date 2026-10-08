# Déployer SENTINEL-X

Windows, PowerShell, depuis la racine du dépôt.

- **PC serveur** : le PC qui fait tourner Docker, la webcam, et qui garde les certificats.
- **ESP32** : la carte capteurs, sur le même Wi-Fi que le PC serveur.
- **Postes** : les PC des collaborateurs qui ouvrent le dashboard.

Ordre : serveur → réseau → ESP32 → postes → utilisation.

---

## 1. Prérequis du PC serveur (une seule fois)

- **Docker Desktop** installé
- **Node.js 20+** (`node -v`)
- **Python 3.10** (`py -3.10 --version`), pour le module vision
- Une **webcam** (sinon, lancer avec `-SansVision`)
- Connecté au **Wi-Fi de l'école** (celui que l'ESP32 utilisera)

## 2. Récupérer le code

```powershell
git clone https://github.com/Swaksm/Workshop-MELTY.git
cd Workshop-MELTY
```

Déjà cloné : `git pull`.

## 3. Lancer le serveur

```powershell
powershell -ExecutionPolicy Bypass -File .\lancer.ps1
```

Au premier lancement, le script crée le `.env`, les mots de passe, les certificats et les fichiers du firmware, puis démarre les conteneurs, le dashboard de dev et le module vision. Détail : [Annexe A](#annexe-a--ce-que-font-les-scripts).

Noter l'IP affichée : `PC détecté sur le Wi-Fi : 10.0.x.x`. C'est l'**IP du serveur**.

| Option | Effet |
|---|---|
| `-SansVision` | pas de webcam / pas de module vision |
| `-SansFront` | pas de dashboard de dev (Vite) |
| `-CameraIndex 1` | utiliser une autre webcam |
| `-ForcerIp 10.0.3.42` | forcer l'IP si la détection Wi-Fi se trompe |

Le premier lancement est long (images Docker, `npm install`, PyTorch + YOLO). Les suivants prennent quelques secondes.

## 4. Vérifier le serveur

```powershell
docker compose ps                      # tous les services "running" / "healthy"
curl http://localhost:8000/health      # {"status":"ok"}
```

Ouvrir http://localhost:5173 et se connecter : `admin` / valeur de `ADMIN_PASSWORD` dans le `.env`.

## 5. Ouvrir le réseau

Docker publie les ports tout seul. Seuls **443** et **8883** sont joignables depuis le Wi-Fi :

| Port | Écoute sur | Service |
|---|---|---|
| 443 | `127.0.0.1` + IP Wi-Fi | HTTPS : dashboard, `/api`, `/vision` (postes) |
| 8883 | `127.0.0.1` + IP Wi-Fi | MQTT TLS (ESP32) |
| 1883 | `127.0.0.1` | MQTT en clair (backend, vision) |
| 8000 | `127.0.0.1` | API / Swagger |
| 8080 | `127.0.0.1` | cAdvisor |
| 5173 | `localhost` | Vite |

Si l'ESP32 ou un poste n'arrive pas à se connecter (Wi-Fi en profil Public : `Get-NetConnectionProfile`), ouvrir le pare-feu une fois, PowerShell **administrateur** :

```powershell
New-NetFirewallRule -DisplayName "SENTINEL-X MQTT TLS" -Direction Inbound -Protocol TCP -LocalPort 8883 -Action Allow -Profile Any
New-NetFirewallRule -DisplayName "SENTINEL-X HTTPS" -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -Profile Any
```

## 6. Installer l'ESP32

À faire **depuis le PC serveur** : les fichiers du firmware y sont déjà générés.

### 6.1 Préparer Arduino IDE (une seule fois)

1. Installer **Arduino IDE 2** : https://www.arduino.cc/en/software
2. *Fichier → Préférences → URL de gestionnaire de cartes supplémentaires*, ajouter :
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
   Puis *Outils → Carte → Gestionnaire de cartes* → installer **esp32** (Espressif Systems).
3. *Croquis → Inclure une bibliothèque → Gérer les bibliothèques*, installer :
   - **PubSubClient** (Nick O'Leary)
   - **DHT sensor library** (Adafruit), accepter « Adafruit Unified Sensor »
   - **Adafruit SSD1306**, accepter « Adafruit GFX Library »
4. Si l'ESP32 n'apparaît pas dans *Outils → Port* : installer le pilote **CP210x** (Silicon Labs) ou **CH340**, selon la puce écrite près du port USB.

### 6.2 Configurer le firmware

1. Créer `secrets.h` (la première fois) :
   ```powershell
   Copy-Item firmware\sentinel_temp\secrets.h.example firmware\sentinel_temp\secrets.h
   ```
2. Le remplir :
   - `WIFI_SSID`, `WIFI_PASSWORD` : Wi-Fi **2,4 GHz** de l'école (l'ESP32 ne voit pas le 5 GHz)
   - `MQTT_HOST` : l'IP du serveur (étape 3). Ensuite `lancer.ps1` la met à jour tout seul
   - `MQTT_PASSWORD` : **copier la valeur de `ESP32_MQTT_PASSWORD` du `.env`** (pas fait automatiquement)
3. Vérifier que `firmware/sentinel_temp/` contient : `sentinel_temp.ino`, `secrets.h`, `ca_cert.h`, `client_cert.h`.

### 6.3 Flasher par câble USB

1. Brancher l'ESP32 (câble USB **data**, pas un câble de charge seule).
2. Ouvrir `firmware/sentinel_temp/sentinel_temp.ino` dans Arduino IDE.
3. *Outils* :
   - Carte : **ESP32 Dev Module**
   - Port : le `COMx` de l'ESP32
   - Partition Scheme : **Default 4MB with spiffs** (si « Sketch too big » : **Minimal SPIFFS (1.9MB APP with OTA)**)
4. **Téléverser** (flèche →). Si bloqué sur `Connecting....` : maintenir le bouton **BOOT** jusqu'au début de l'écriture.

### 6.4 Vérifier l'ESP32

1. *Outils → Moniteur série*, **115200 bauds** : connexion Wi-Fi puis MQTT réussies.
2. Sur le dashboard, les mesures arrivent.

## 7. Donner l'accès aux collaborateurs

Le dashboard HTTPS (`https://<IP du serveur>`) n'accepte que les postes qui ont un certificat. 5 sont générés (`NB_CLIENTS` dans le `.env`).

### 7.1 Les certificats

Tous sur le PC serveur, jamais commités.

| Fichier | Rôle | Que faire |
|---|---|---|
| `mosquitto/certs/ca.key` | clé de l'autorité de certification | **ne jamais partager, ne jamais copier.** La perdre = tout regénérer et tout redistribuer |
| `mosquitto/certs/ca.crt` | certificat de la CA (public) | à donner à chaque collaborateur |
| `mosquitto/certs/server.crt` / `.key` | certificat du broker et du HTTPS | rien, reste sur le serveur |
| `mosquitto/certs/clients/posteN.p12` | certificat d'un collaborateur | **un par personne**, à lui donner |
| `mosquitto/certs/clients/posteN.mot-de-passe.txt` | mot de passe du `.p12` | à donner **séparément** (pas sur la même clé USB / pas dans le même message) |
| `mosquitto/certs/clients/posteN.crt` | sert au serveur à reconnaître le poste | reste sur le serveur. Le supprimer = révoquer le poste |
| `mosquitto/certs/clients/esp32.crt` / `.key` | identité de l'ESP32 | rien, copiés dans `client_cert.h` |
| `firmware/sentinel_temp/ca_cert.h` | CA pour le firmware | utilisé au flash |
| `firmware/sentinel_temp/client_cert.h` | certificat + **clé privée** de l'ESP32 | utilisé au flash. Secret : ne pas diffuser |

### 7.2 Installer un poste

1. Lui remettre `posteN.p12` + `ca.crt` (clé USB), et le mot de passe à part. Un numéro différent par personne.
2. Sur son PC, PowerShell, dans le dossier des fichiers :
   ```powershell
   Import-PfxCertificate -FilePath .\posteN.p12 -CertStoreLocation Cert:\CurrentUser\My -Password (Read-Host -AsSecureString "Mot de passe")
   Import-Certificate -FilePath .\ca.crt -CertStoreLocation Cert:\CurrentUser\Root
   ```
   Firefox a son propre magasin : Paramètres → Certificats → Afficher les certificats → Vos certificats → Importer.
3. Fermer **tous** les onglets du navigateur, le rouvrir, aller sur `https://<IP du serveur>`, choisir « Sentinel-X posteN ».
4. Une fois distribués : supprimer du serveur `posteN.p12`, `posteN.key` et `posteN.mot-de-passe.txt` (garder `posteN.crt`).

## 8. Utiliser

| Quoi | Adresse | Depuis |
|---|---|---|
| Dashboard HTTPS | `https://<IP du serveur>` (ou https://localhost) | postes autorisés |
| Dashboard de dev | http://localhost:5173 | PC serveur |
| Swagger (API) | http://localhost:8000/docs | PC serveur |
| Supervision des conteneurs | http://localhost:8080 | PC serveur |

**Connexion** : `admin` / valeur de `ADMIN_PASSWORD` dans le `.env`.

## 9. Au quotidien

### Démarrer / arrêter

```powershell
powershell -ExecutionPolicy Bypass -File .\lancer.ps1     # démarrer
powershell -ExecutionPolicy Bypass -File .\arreter.ps1    # arrêter
```

Les données (base, modèles) sont conservées. Pour tout effacer : `docker compose down -v`.

### Reflasher l'ESP32 quand…

- `lancer.ps1` affiche « reflasher l'ESP32 » (IP du serveur changée, `ca_cert.h` ou `client_cert.h` régénérés)
- `ESP32_MQTT_PASSWORD` a changé dans le `.env` (le recopier dans `secrets.h` avant)
- le code `.ino` a changé

Par câble (étape 6.3) ou **sans câble (OTA)**, si un firmware tourne déjà et que l'ESP32 est sur le même Wi-Fi :

1. *Outils → Port* → port réseau **SentinelG999** (absent = le Wi-Fi bloque la découverte : passer par le câble).
2. Téléverser, mot de passe = `OTA_PASSWORD` de `secrets.h`.

### Flasher depuis un autre PC

Lui donner par clé USB **les 3 fichiers** `secrets.h`, `ca_cert.h`, `client_cert.h` du PC serveur, à mettre dans son `firmware/sentinel_temp/`. Ils contiennent la clé de l'ESP32 et les mots de passe : les supprimer de la clé USB après. Puis étapes 6.1 et 6.3. À refaire à chaque changement d'IP du serveur.

## 10. Développer

| Je modifie… | Pour voir le changement |
|---|---|
| `frontend/` | rien à faire, Vite (http://localhost:5173) recharge tout seul |
| `backend/` | `docker compose up -d --build backend` |
| `vision/` | `.\arreter.ps1` puis `.\lancer.ps1` |
| `proxy/Caddyfile` ou le front compilé (443) | `docker compose up -d --build proxy` |
| `firmware/` | reflasher (étape 6.3) |

Journaux :

```powershell
docker compose logs -f backend         # ou mosquitto, proxy, db
Get-Content logs\vision.err -Wait      # module vision
Get-Content logs\front.log -Wait       # Vite
```

Tests :

```powershell
# Backend (dans l'image Docker)
docker compose build backend
docker run --rm -v "${PWD}\backend:/code" -w /code sentinelx-backend sh -c "pip install -q -r requirements-dev.txt && pytest"

# Vision
cd vision
.venv\Scripts\python.exe -m pip install pytest==8.3.4
.venv\Scripts\python.exe -m pytest
cd ..
```

---

## Annexe A : ce que font les scripts

### `lancer.ps1`

1. **Docker** : démarre Docker Desktop s'il ne répond pas (attend jusqu'à 3 min).
2. **IP** : détecte l'IP du PC sur le Wi-Fi et l'écrit dans `SERVER_IP` du `.env` (`127.0.0.2` si pas de Wi-Fi). Prévient si elle a changé.
3. **`.env`** : le crée depuis `.env.example` s'il manque, puis génère les secrets encore à `change-me` : `MQTT_PASSWORD`, `VISION_MQTT_PASSWORD`, `ESP32_MQTT_PASSWORD`, `ADMIN_PASSWORD`, `JWT_SECRET`. Fixe `MQTT_USER=backend` et `ADMIN_USER=admin`.
4. **Comptes MQTT** : recrée `mosquitto/passwd` (comptes `backend`, `vision`, `esp32`).
5. **Certificats** (`mosquitto/certs/`) : crée ceux qui manquent (CA, serveur, ESP32, `poste1` à `poste5`). Refait le certificat serveur si l'IP a changé.
6. **Firmware** : met à jour `ca_cert.h`, `client_cert.h` et `MQTT_HOST` dans `secrets.h` (dans `firmware/sentinel_temp/`). S'il annonce un changement, reflasher l'ESP32.
7. **Conteneurs** : `docker compose up -d --build` (db, mosquitto, backend, proxy, cadvisor). Redémarre mosquitto et proxy si les certificats ont changé.
8. **Dashboard de dev** : `npm install` si `node_modules` manque, puis Vite en arrière-plan sur `localhost:5173`.
9. **Vision** : crée `vision/.venv` et installe les dépendances la première fois, puis lance `vision/app.py` en arrière-plan.

Il ne touche pas au pare-feu Windows (voir étape 5).

### `arreter.ps1`

1. Tue les processus Vite et vision lancés par `lancer.ps1`.
2. `docker compose down` : arrête et supprime les conteneurs, **garde les volumes** (base, modèles).

Il ne touche ni au `.env`, ni aux certificats, ni au pare-feu.

## Annexe B : en cas de problème

| Symptôme | Solution |
|---|---|
| « Docker ne répond pas » | redémarrer Windows (ne pas réinitialiser Docker : ça efface les volumes) |
| `SERVER_IP` manquante | lancer via `lancer.ps1`, pas `docker compose up` directement |
| « Wi-Fi inactif » | se connecter au Wi-Fi, ou `-ForcerIp <IP>` |
| « No suitable Python runtime found » | Python 3.10 absent : `winget install Python.Python.3.10`, rouvrir PowerShell |
| ESP32 : Wi-Fi OK mais MQTT en échec | IP changée sans reflash, `MQTT_PASSWORD` ≠ `ESP32_MQTT_PASSWORD`, ou pare-feu (étape 5) |
| Un poste n'atteint pas `https://<IP>` | pare-feu (étape 5), ou mauvaise IP |
| `ERR_BAD_SSL_CLIENT_AUTH_CERT` | certificat de poste absent ou révoqué : étape 7.2 |
| `NET::ERR_CERT_AUTHORITY_INVALID` | `ca.crt` pas importé sur ce poste : étape 7.2 |
| Écran de connexion qui revient | session expirée (8 h) : se reconnecter |
| Webcam non détectée | `.\arreter.ps1` puis `.\lancer.ps1` (scan au démarrage uniquement) |

Plus de détails : [README.md](README.md).
