# SENTINEL-X

Surveillance d'une table de capteurs : un ESP32 relève température, humidité et gaz, un modèle d'IA détecte les anomalies, un buzzer alerte sur place et un dashboard affiche l'état en temps réel.

Projet du workshop EPSI Bac+4 (mission AetherCorp). Le sujet impose notamment : pas de seuils statiques, chiffrement des flux, stack conteneurisée.

## Sommaire

1. [Architecture](#1-architecture)
2. [Stack](#2-stack)
3. [Structure du dépôt](#3-structure-du-dépôt)
4. [Installation et lancement](#4-installation-et-lancement)
5. [Configuration](#5-configuration)
6. [Flux de données](#6-flux-de-données)
7. [Protocole MQTT](#7-protocole-mqtt)
8. [Base de données](#8-base-de-données)
9. [API REST et Swagger](#9-api-rest-et-swagger)
10. [Modèle d'IA](#10-modèle-dia)
11. [Tests et CI/CD](#11-tests-et-cicd)
12. [Simulateur](#12-simulateur)
13. [Limites connues](#13-limites-connues)
14. [Feuille de route](#14-feuille-de-route)

## 1. Architecture

```
ESP32 (AM2302, MQ-2, buzzer)
   │  WiFi · MQTT   sentinelx/<table>/sensors   (JSON toutes les 5 s)
   ▼
Mosquitto  ── broker MQTT (1883)  ◄── sentinelx/<table>/cmd  (commande buzzer)
   │
   ▼
Backend FastAPI (8000)
   ├── réception MQTT ──► PostgreSQL (measurements, alerts)
   ├── modèle LOF par table ──► anomalie ──► alerte + buzzer on
   └── API REST /api/v1  ──► Swagger /docs
          ▲
Frontend React (Vite, 5173) ── proxy /api ──► backend
```

Le PC serveur est un PC portable d'un apprenant : il héberge la stack Docker et crée le WiFi de la table. L'ESP32 se connecte à ce WiFi et publie vers le broker. Le boîtier ne contient que l'ESP32 et les capteurs.

## 2. Stack

| Couche | Technologies |
|---|---|
| Firmware | C++ (Arduino, ESP32), PubSubClient, ArduinoJson, DHT |
| Broker | Eclipse Mosquitto 2 |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, paho-mqtt 2, scikit-learn 1.6 |
| Base de données | PostgreSQL 16 |
| Frontend | React 18, Vite 5, Recharts |
| Tests et CI | pytest, GitHub Actions, GHCR |
| Infra | Docker Compose |

## 3. Structure du dépôt

```
.
├── backend/
│   ├── app/
│   │   ├── main.py         # routes FastAPI et cycle de vie (démarrage MQTT, création des tables)
│   │   ├── mqtt.py         # abonnement aux capteurs, publication des commandes buzzer
│   │   ├── detection.py    # évaluation d'une mesure, création d'alertes, état actif
│   │   ├── ml.py           # features, entraînement, chargement et sauvegarde du modèle
│   │   ├── models.py       # tables measurements et alerts (SQLAlchemy)
│   │   ├── schemas.py      # schémas Pydantic d'entrée et de sortie
│   │   ├── db.py           # moteur et session SQLAlchemy
│   │   └── config.py       # variables d'environnement
│   ├── tests/              # tests pytest (modèle, API, détection)
│   ├── Dockerfile
│   ├── pytest.ini
│   ├── requirements.txt
│   └── requirements-dev.txt
├── frontend/
│   ├── src/App.jsx         # écran de supervision
│   ├── src/api.js          # appels à l'API
│   ├── src/styles.css
│   └── vite.config.js      # proxy /api → localhost:8000
├── mosquitto/
│   └── mosquitto.conf      # configuration du broker (développement)
├── tools/
│   └── simulate_sensors.py # publie de fausses mesures sur le broker
├── .github/workflows/ci.yml
├── docker-compose.yml
├── .env.example
└── README.md
```

## 4. Installation et lancement

### Prérequis

- Docker Desktop, ou Docker Engine et Compose v2
- Node.js 20 ou plus, pour le frontend
- Un WiFi 2,4 GHz pour l'ESP32 : sur Windows, Paramètres → Point d'accès mobile

### Étapes

```bash
git clone https://github.com/Swaksm/Workshop-MELTY.git
cd Workshop-MELTY
cp .env.example .env
docker compose up --build -d
```

Le backend est prêt quand ceci répond :

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Frontend, dans un second terminal :

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Ouvre http://localhost:5173.

### Services

| Service | Port hôte | Rôle |
|---|---|---|
| `backend` | 8000 | API REST, Swagger |
| `mosquitto` | 1883 | broker MQTT |
| `db` | non exposé | PostgreSQL, accessible uniquement depuis le réseau Docker |

### Arrêter

```bash
docker compose down        # arrête les conteneurs, garde les données
docker compose down -v     # supprime aussi la base et les modèles entraînés
```

### Réseau de la table

Toute la communication se fait sur un seul réseau local, créé par le PC serveur. Rien ne sort vers internet : l'ESP32, le PC et les autres appareils de la table sont sur le même sous-réseau.

#### Plan d'adressage

| Équipement | Adresse | Rôle |
|---|---|---|
| Passerelle / PC serveur | `192.168.52.1` (à vérifier) | héberge Mosquitto (1883) et l'API (8000), crée le hotspot |
| ESP32 | `192.168.52.50` | IP fixe, publie les mesures |
| Autres appareils | DHCP, par exemple `192.168.52.x` | consultent l'API depuis le navigateur |
| Masque | `255.255.255.0` (`/24`) | tous les appareils de la table |
| DNS | `8.8.8.8` (inutile hors internet) | ignoré pour le fonctionnement local |

Le plan ci-dessus est la cible du projet. **Windows peut attribuer une autre adresse au hotspot** (par défaut `192.168.137.1`). L'adresse réelle est celle que tu lis avec `ipconfig` : le firmware doit la reprendre.

#### Créer le hotspot

1. Paramètres → Réseau et Internet → **Point d'accès mobile**.
2. Nom du réseau : `Sentinel_G9`, mot de passe : `Sentinel_G9`.
3. Bande : **2,4 GHz** (l'ESP32 ne supporte pas la 5 GHz).
4. Active le point d'accès.

Certaines cartes Wi-Fi ne peuvent pas être connectées au Wi-Fi de l'école et diffuser le hotspot en même temps. Dans ce cas, le hotspot ne démarre pas, ou n'obtient pas d'adresse.

#### Vérifier l'adresse du PC

```powershell
ipconfig
```

Cherche la carte « Connexion au réseau local* N » dont le statut est **connecté** et qui a une adresse IPv4. C'est l'adresse du PC serveur sur le hotspot.

- `Média déconnecté` : le hotspot n'est pas actif.
- `192.168.52.1` : le firmware est correct.
- `192.168.137.1` (ou autre) : le firmware doit être adapté, voir ci-dessous.

#### Adapter le firmware à l'adresse réelle

Trois valeurs dans `sentinel_temp.ino` (ou le firmware équivalent), à remplacer par le préfixe réel. Exemple avec `192.168.137.1` :

| Variable | Valeur |
|---|---|
| `local_IP` | `192.168.137.50` |
| `gateway` | `192.168.137.1` |
| `MQTT_HOST` | `192.168.137.1` |

Le masque ne change pas. L'ESP32 doit être dans le même sous-réseau que le PC.

#### Ouvrir les ports (pare-feu Windows)

L'ESP32 doit atteindre le port MQTT, et les autres appareils le port de l'API. Une fois, dans un terminal **administrateur** :

```powershell
New-NetFirewallRule -DisplayName "SENTINEL-X MQTT" -Direction Inbound -Protocol TCP -LocalPort 1883 -Action Allow -Profile Private
New-NetFirewallRule -DisplayName "SENTINEL-X API" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow -Profile Private
```

Le profil « Privé » doit être actif pour le hotspot. Sinon, remplace `-Profile Private` par `-Profile Any`.

#### Qui parle à qui

| De | Vers | Protocole et port | Usage |
|---|---|---|---|
| ESP32 `192.168.52.50` | PC `192.168.52.1:1883` | MQTT (TCP) | publie `sentinelx/table1/sensors` |
| Backend (conteneur) | `mosquitto:1883` | MQTT (réseau Docker) | reçoit les mesures |
| Backend (conteneur) | `db:5432` | PostgreSQL (réseau Docker) | enregistre les mesures |
| Backend (conteneur) | `mosquitto:1883` | MQTT (réseau Docker) | envoie les commandes buzzer |
| Mosquitto | ESP32 | MQTT (TCP) | commande sur `sentinelx/table1/cmd` (l'ESP32 doit s'y abonner) |
| Navigateur du PC | `localhost:8000` | HTTP | API et Swagger |
| Autre appareil | `192.168.52.1:8000` | HTTP | API et Swagger |

Le backend parle à Mosquitto et à la base par les **noms de service Docker**, pas par l'IP du PC. Seuls l'ESP32 et les autres appareils utilisent l'IP du PC.

#### Vérifier que tout communique

Depuis le PC, dans l'ordre :

```powershell
ipconfig                                  # l'adresse du hotspot est bien celle attendue
Test-NetConnection 192.168.52.1 -Port 1883   # le port MQTT répond (adapte l'IP)
curl http://localhost:8000/health         # l'API répond
```

Depuis l'ESP32, le moniteur série doit afficher l'IP fixe, puis `Connexion MQTT... OK`.

#### Problèmes courants

| Symptôme | Cause probable |
|---|---|
| Le hotspot ne démarre pas | la carte Wi-Fi partage déjà la connexion de l'école |
| L'ESP32 se connecte au WiFi, mais `Connexion MQTT... échec` | mauvaise adresse du PC dans le firmware, ou pare-feu qui bloque 1883 |
| `Test-NetConnection` échoue | `docker compose up -d` pas lancé, ou pare-feu |
| L'ESP32 n'obtient pas le WiFi | hotspot en 5 GHz, ou mauvais mot de passe |
| Les autres appareils ne joignent pas l'API | pare-feu qui bloque 8000, ou profil réseau « Public » |

#### Limites

- Le réseau n'a pas d'accès internet : seules les machines de la table communiquent.
- L'adresse du PC change si le hotspot est recréé avec un autre plan d'adressage. Le firmware doit alors être mis à jour.
- Le broker n'est pas chiffré (MQTT en clair) : c'est une limite connue, voir [Limites](#13-limites-connues).

## 5. Configuration

Fichier `.env` à la racine, créé à partir de `.env.example`. Il n'est pas versionné.

| Variable | Exemple | Utilisée par | Rôle |
|---|---|---|---|
| `POSTGRES_USER` | `sentinel` | `db` | utilisateur PostgreSQL |
| `POSTGRES_PASSWORD` | `change-me` | `db` | mot de passe PostgreSQL |
| `POSTGRES_DB` | `sentinel` | `db` | nom de la base |
| `DATABASE_URL` | `postgresql+psycopg://sentinel:…@db:5432/sentinel` | `backend` | connexion SQLAlchemy |
| `MQTT_HOST` | `mosquitto` | `backend` | hôte du broker vu depuis le backend |
| `MQTT_PORT` | `1883` | `backend` | port MQTT |

## 6. Flux de données

### Chemin d'une mesure

1. **Capture** : l'ESP32 lit l'AM2302 (température, humidité) et le MQ-2 (gaz, valeur ADC brute).
2. **Publication** : toutes les 5 s, il envoie un JSON sur `sentinelx/<table>/sensors`.
3. **Réception** : le backend, abonné à `sentinelx/+/sensors`, extrait le `table_id` du topic (le deuxième segment) et valide le payload avec `MeasurementIn` (`temp` float, `hum` float, `gas` entier).
4. **Stockage** : la mesure est insérée dans `measurements`, avec `received_at` = heure de réception côté serveur.
5. **Évaluation** : si un modèle existe pour la table, les 30 dernières mesures sont lues en base et le modèle décide normal ou anomalie (voir [Modèle d'IA](#10-modèle-dia)).
6. **Alerte** : au passage en anomalie, une ligne est ajoutée dans `alerts`, et le backend publie `{"buzzer":"on"}` sur `sentinelx/<table>/cmd`. Au retour à la normale, il publie `{"buzzer":"off"}`.
7. **Lecture** : le frontend interroge l'API toutes les 3 s et affiche les données.

### Cas d'erreur

| Situation | Comportement |
|---|---|
| Payload non JSON, champ manquant ou mauvais type | le message est ignoré, un warning est journalisé, rien n'est stocké |
| `gas` envoyé avec une décimale (ex. `1234.5`) | rejeté : le champ est un entier |
| Broker indisponible au démarrage | le backend réessaie en tâche de fond, sans bloquer l'API |
| Backend redémarré | les mesures sont conservées ; le modèle est rechargé depuis le disque ; l'état d'alerte repart à zéro |

### Commandes

Une commande part de l'API (`POST /tables/{table_id}/commande`) ou du moteur de détection. Elle est publiée sur `sentinelx/<table>/cmd`. L'ESP32 doit s'abonner à ce topic et actionner le buzzer.

## 7. Protocole MQTT

Une **table** est un identifiant libre (`table1`, `table2`…). Il doit être identique côté ESP32, backend et frontend.

| Sens | Topic | Payload | Fréquence |
|---|---|---|---|
| ESP32 → backend | `sentinelx/<table>/sensors` | `{"temp":23.4,"hum":51.2,"gas":1234}` | toutes les 5 s |
| backend → ESP32 | `sentinelx/<table>/cmd` | `{"buzzer":"on"}` ou `{"buzzer":"off"}` | sur événement |

Règles :
- `temp` : °C, un chiffre après la virgule.
- `hum` : pourcentage d'humidité relative.
- `gas` : valeur ADC brute, entier de 0 à 4095. Pas de conversion en ppm.
- Si la lecture du capteur échoue, n'envoie rien pour ce cycle.
- Le broker de développement accepte les connexions anonymes sur 1883 (voir [Limites](#13-limites-connues)).

Test manuel avec Mosquitto installé sur le PC :

```bash
mosquitto_sub -h localhost -t "sentinelx/#" -v
mosquitto_pub -h localhost -t "sentinelx/table1/cmd" -m '{"buzzer":"on"}'
```

## 8. Base de données

PostgreSQL 16. Les tables sont créées au démarrage du backend (`Base.metadata.create_all`). Il n'y a pas encore de migrations.

### Table `measurements`

Une ligne par mesure reçue.

| Colonne | Type | Contrainte | Description |
|---|---|---|---|
| `id` | `integer` | clé primaire, auto-incrémentée | identifiant interne, sert d'ordre d'insertion |
| `table_id` | `varchar(64)` | non null, indexée | table qui a émis la mesure |
| `temp` | `double precision` | non null | température en °C |
| `hum` | `double precision` | non null | humidité en % |
| `gas` | `integer` | non null | valeur ADC brute du MQ-2 |
| `received_at` | `timestamptz` | non null, défaut `now()`, indexée | heure de réception par le backend |

Index : `measurements_pkey` (id), `ix_measurements_table_id`, `ix_measurements_received_at`.

### Table `alerts`

Une ligne par passage en anomalie. Un retour à la normale ne crée pas de ligne.

| Colonne | Type | Contrainte | Description |
|---|---|---|---|
| `id` | `integer` | clé primaire, auto-incrémentée | identifiant |
| `table_id` | `varchar(64)` | non null, indexée | table concernée |
| `temp` | `double precision` | non null | température de la mesure déclenchante |
| `hum` | `double precision` | non null | humidité de la mesure déclenchante |
| `gas` | `integer` | non null | gaz de la mesure déclenchante |
| `created_at` | `timestamptz` | non null, défaut `now()`, indexée | heure de création de l'alerte |

Index : `alerts_pkey` (id), `ix_alerts_table_id`, `ix_alerts_created_at`.

### Ce qui n'est pas en base

| Élément | Où il est | Conséquence |
|---|---|---|
| Modèle entraîné | `backend/models/<table>.joblib` (volume `model-data`) | survit aux redémarrages, mais pas à `down -v` |
| État « alerte active » | mémoire du backend | repart à faux après un redémarrage |
| Cache des modèles | mémoire du backend | rechargé depuis le disque à la demande |

### Volumétrie et rétention

Une table à 1 mesure toutes les 5 s produit environ 17 000 lignes par jour dans `measurements`. Il n'existe pas encore de purge : pour un workshop d'une semaine, ça reste faible, mais une purge est à prévoir.

### Accéder à la base

```bash
docker compose exec db psql -U sentinel -d sentinel
```

```sql
SELECT table_id, count(*) FROM measurements GROUP BY table_id;
SELECT * FROM alerts ORDER BY created_at DESC LIMIT 10;
```

## 9. API REST et Swagger

L'API est documentée automatiquement par FastAPI.

| URL | Contenu |
|---|---|
| http://localhost:8000/docs | **Swagger UI** : toutes les routes, schémas, et bouton « Try it out » |
| http://localhost:8000/redoc | même documentation, en lecture seule |
| http://localhost:8000/openapi.json | spécification OpenAPI brute, à importer dans Postman ou un générateur de client |

Base : `http://localhost:8000/api/v1`. Titre de l'API : `SENTINEL-X API`, version `0.1.0`.

### Routes

| Méthode | Route | Rôle | Réponse |
|---|---|---|---|
| GET | `/health` | état du service | `{"status":"ok"}` |
| GET | `/api/v1/mesures?table_id=&limit=` | dernières mesures, plus récentes d'abord | liste de `MeasurementOut` |
| GET | `/api/v1/alertes?table_id=&limit=` | dernières alertes, plus récentes d'abord | liste de `AlertOut` |
| GET | `/api/v1/tables/{table_id}/etat` | état d'une table | `EtatOut` |
| POST | `/api/v1/tables/{table_id}/entrainement` | entraîne le modèle sur les mesures stockées | `EntrainementOut` |
| POST | `/api/v1/tables/{table_id}/commande` | commande le buzzer | `202` avec `{"buzzer":"on"}` |

Paramètres :
- `table_id` (optionnel sur `/mesures` et `/alertes`) : filtre sur une table.
- `limit` : `/mesures` vaut 100 par défaut, 1000 au maximum ; `/alertes` vaut 50 par défaut, 500 au maximum.

### Schémas

**`MeasurementOut`**

```json
{"id": 204, "table_id": "table1", "temp": 23.4, "hum": 51.2, "gas": 1234, "received_at": "2026-10-05T12:52:28Z"}
```

**`AlertOut`**

```json
{"id": 3, "table_id": "table1", "temp": 23.1, "hum": 50.2, "gas": 3500, "created_at": "2026-10-05T12:43:45Z"}
```

**`EtatOut`**

```json
{"alerte_active": true, "modele_entraine": true}
```

**`EntrainementOut`**

```json
{"mesures_utilisees": 153}
```

**`CommandeIn`** (corps de la requête `commande`)

```json
{"buzzer": "on"}
```

Seules valeurs acceptées : `"on"` ou `"off"`. Toute autre valeur donne une erreur `422`.

### Codes d'erreur

| Code | Quand |
|---|---|
| `400` | entraînement avec moins de 100 mesures, avec le détail du nombre actuel |
| `422` | corps ou paramètres invalides (détail dans la réponse) |
| `500` | erreur interne ; les logs du backend donnent la trace |

### Exemples

```bash
curl "http://localhost:8000/api/v1/mesures?table_id=table1&limit=5"
curl "http://localhost:8000/api/v1/alertes?table_id=table1"
curl http://localhost:8000/api/v1/tables/table1/etat
curl -X POST http://localhost:8000/api/v1/tables/table1/entrainement
curl -X POST http://localhost:8000/api/v1/tables/table1/commande \
     -H "Content-Type: application/json" -d '{"buzzer":"on"}'
```

L'API n'a pas encore d'authentification : elle est prévue pour un usage local, sur le WiFi de la table.

## 10. Modèle d'IA

Le modèle ne contient aucun seuil écrit à la main. Il apprend ce qui est normal pour une table, puis signale ce qui s'en écarte.

### Entrée

À chaque mesure, on prend les 30 dernières de la table (environ 2,5 minutes). Cinq valeurs sont calculées :
- température, humidité et gaz de la mesure courante ;
- pente de la température et pente du gaz sur la fenêtre (la tendance).

### Algorithme

Pipeline scikit-learn : `StandardScaler` puis `LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.05)`.

Un point est une anomalie s'il se trouve dans une zone beaucoup moins dense que ses 20 voisins les plus proches appris pendant l'entraînement.

### Entraînement

`POST /api/v1/tables/{table_id}/entrainement` :
1. lit jusqu'à 5000 mesures de la table, les plus récentes ;
2. calcule les 5 valeurs pour chacune ;
3. entraîne le pipeline ;
4. l'enregistre dans `backend/models/<table>.joblib`.

Minimum : 100 mesures. Pour une table, le réentraînement remplace le modèle précédent.

### Détection

À chaque mesure reçue :
- **passage en anomalie** : une ligne dans `alerts`, puis `buzzer on` ;
- **retour à la normale** : `buzzer off`.

Une alerte n'est créée qu'au passage en anomalie, pas à chaque mesure anormale.

### Bonnes pratiques d'entraînement

Entraîne sur une période normale : pas de test au gaz, pas de passage d'humain dans le champ, pas de pic simulé. Ce qui est dans les données d'entraînement est appris comme normal.

### Choix du modèle

Sur des données simulées, Isolation Forest détectait 94 % des pics avec 6,8 % de fausses alertes. LOF détecte 100 % des pics avec 0,5 % de fausses alertes. Ces chiffres viennent de données simulées : il faudra les revérifier avec les vraies mesures du capteur.

## 11. Tests et CI/CD

### Tests backend

12 tests pytest : modèle (pic détecté, normal accepté, rechargement), API (routes, validation, commande) et détection (alerte, puis retour à `off`). Les tests utilisent une base SQLite temporaire et ne démarrent pas le MQTT.

Lancer en local (Python 3.12) :

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Ou dans l'image Docker, sans rien installer sur le PC :

```bash
docker compose build backend
docker run --rm -v "$PWD/backend:/code" -w /code workshop-backend \
  sh -c "pip install -q -r requirements-dev.txt && pytest"
```

Sous Git Bash (Windows), préfixe la commande par `MSYS_NO_PATHCONV=1` pour éviter la réécriture du chemin `/code`.

### Workflow GitHub Actions

Fichier `.github/workflows/ci.yml`. Il se lance sur chaque push et pull request vers `main`.

| Job | Ce qu'il vérifie |
|---|---|
| `backend-tests` | `pytest` |
| `frontend-build` | `npm ci` puis `npm run build` |
| `stack-e2e` | démarre la stack Docker, attend `/health`, publie une mesure MQTT et vérifie qu'elle arrive dans l'API, puis entraîne le modèle sur 120 mesures |
| `publish-image` | sur `main` seulement, si tout est vert : publie l'image backend sur GHCR (`ghcr.io/swaksm/sentinel-x-backend`, tags `latest` et `<sha>`) |

En cas d'échec de `stack-e2e`, les logs des conteneurs sont affichés. La stack est toujours arrêtée à la fin, avec ses volumes.

## 12. Simulateur

Sans ESP32, `tools/simulate_sensors.py` publie des mesures normales toutes les 5 s. Avec `--pic`, il envoie un pic de gaz à 60 s.

Il tourne dans le conteneur backend, car paho-mqtt n'est pas sur l'hôte :

```bash
docker compose exec -T backend python - --host mosquitto --pic < tools/simulate_sensors.py
```

Options : `--table` (défaut `table1`), `--host` (défaut `localhost`), `--port` (défaut 1883), `--intervalle` (défaut 5 s), `--pic`.

Scénario de test complet :
1. Laisse tourner environ 2 minutes pour dépasser 100 mesures.
2. Entraîne : `POST /api/v1/tables/table1/entrainement`.
3. Attends le pic à 60 s, puis vérifie : `GET /api/v1/tables/table1/etat` doit renvoyer `"alerte_active": true`.

## 13. Limites connues

- **Fausse alerte après un pic** : pendant que le pic sort de la fenêtre de 30 mesures, la pente change et une mesure normale peut être signalée.
- **État d'alerte en mémoire** : non persisté, repart à faux après un redémarrage.
- **MQTT en clair, sans authentification** : Mosquitto accepte les connexions anonymes sur 1883. Le sujet exige MQTTS et des identifiants.
- **API sans authentification.**
- **Pas de migrations** : le schéma est créé par `create_all`. Un changement de schéma impose de supprimer le volume `pgdata`.
- **Pas de purge** des mesures.
- **Un seul modèle par table**, sans versionnage ni rollback.
- **Pas de firmware ESP32 dans ce dépôt** : le protocole ci-dessus est la seule interface attendue.
- **Pas de module vision (webcam)** pour l'instant.
- **Frontend** : une seule table codée en dur (`table1`) dans `App.jsx`. Pas encore de conteneur Docker pour le frontend.

## 14. Feuille de route

1. Firmware ESP32 : lecture des capteurs, publication, buzzer.
2. TLS sur MQTT, authentification du broker.
3. Authentification de l'API, migrations Alembic, purge des mesures.
4. Correction de la fausse alerte après un pic.
5. Sélection de la table dans le frontend, conteneur Docker du frontend.
6. Module vision (webcam), si retenu.
