# SENTINEL-X

Surveillance d'une table de capteurs : un ESP32 relève température, humidité et gaz, un modèle d'IA détecte les anomalies, un buzzer alerte sur place et un dashboard affiche l'état en temps réel.

Projet du workshop EPSI Bac+4 (mission AetherCorp). Le sujet impose notamment : pas de seuils statiques, chiffrement des flux, stack conteneurisée.

## Sommaire

- [Architecture](#architecture)
- [Stack](#stack)
- [Structure du dépôt](#structure-du-dépôt)
- [Installation](#installation)
- [Configuration](#configuration)
- [Protocole MQTT](#protocole-mqtt)
- [API REST](#api-rest)
- [Modèle d'IA](#modèle-dia)
- [Tests avec le simulateur](#tests-avec-le-simulateur)
- [Limites connues](#limites-connues)

## Architecture

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
   └── API REST /api/v1
          ▲
Frontend React (Vite, 5173) ── proxy /api ──► backend
```

Le PC serveur est un PC portable d'un apprenant : il héberge la stack Docker et crée le WiFi de la table. L'ESP32 se connecte à ce WiFi et publie vers le broker. Le boîtier ne contient que l'ESP32 et les capteurs.

## Stack

| Couche | Technologies |
|---|---|
| Firmware | C++ (Arduino, ESP32), PubSubClient, ArduinoJson, DHT |
| Broker | Eclipse Mosquitto 2 |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, paho-mqtt 2, scikit-learn 1.6 |
| Base de données | PostgreSQL 16 |
| Frontend | React 18, Vite 5, Recharts |
| Infra | Docker Compose |

## Structure du dépôt

```
.
├── backend/
│   ├── app/
│   │   ├── main.py        # API FastAPI, routes et cycle de vie
│   │   ├── mqtt.py        # abonnement capteurs, publication buzzer
│   │   ├── detection.py   # évaluation d'une mesure, création d'alertes
│   │   ├── ml.py          # features, entraînement, chargement du modèle
│   │   ├── models.py      # tables measurements et alerts
│   │   ├── schemas.py     # schémas Pydantic (entrée/sortie)
│   │   ├── db.py          # moteur SQLAlchemy
│   │   └── config.py      # variables d'environnement
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/              # dashboard React (Vite)
│   ├── src/App.jsx        # écran de supervision
│   ├── src/api.js         # appels à l'API
│   └── vite.config.js     # proxy /api → localhost:8000
├── mosquitto/
│   └── mosquitto.conf     # configuration du broker (dev)
├── tools/
│   └── simulate_sensors.py  # publie de fausses mesures
├── docker-compose.yml
├── .env.example
└── README.md
```

## Installation

### Prérequis

- Docker Desktop (ou Docker Engine + Compose v2)
- Node.js 20 ou plus, pour le frontend
- Un PC avec un point d'accès WiFi 2,4 GHz pour l'ESP32 (sur Windows : Paramètres → Point d'accès mobile)

### 1. Cloner et configurer

```bash
git clone https://github.com/Swaksm/Workshop-MELTY.git
cd Workshop-MELTY
cp .env.example .env
```

Modifie `.env` si nécessaire (voir [Configuration](#configuration)).

### 2. Lancer le backend

```bash
docker compose up --build -d
```

Services démarrés :

| Service | Port hôte | Rôle |
|---|---|---|
| `backend` | 8000 | API REST |
| `mosquitto` | 1883 | broker MQTT |
| `db` | interne | PostgreSQL |

Vérification :

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Les tables sont créées au démarrage. Il n'y a pas encore de migrations.

### 3. Lancer le frontend

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Ouvre http://localhost:5173. Le frontend interroge l'API toutes les 3 secondes.

### 4. Arrêter

```bash
docker compose down        # garde les données
docker compose down -v     # supprime aussi la base et les modèles
```

## Configuration

Fichier `.env` (non versionné), à partir de `.env.example` :

| Variable | Exemple | Rôle |
|---|---|---|
| `POSTGRES_USER` | `sentinel` | utilisateur PostgreSQL |
| `POSTGRES_PASSWORD` | `change-me` | mot de passe PostgreSQL |
| `POSTGRES_DB` | `sentinel` | nom de la base |
| `DATABASE_URL` | `postgresql+psycopg://sentinel:…@db:5432/sentinel` | connexion SQLAlchemy |
| `MQTT_HOST` | `mosquitto` | hôte du broker vu depuis le backend |
| `MQTT_PORT` | `1883` | port MQTT |

Le `.env` ne doit jamais être versionné.

## Protocole MQTT

Une **table** est un identifiant libre (`table1`, `table2`…). Chaque table a deux topics :

| Sens | Topic | Payload | Fréquence |
|---|---|---|---|
| ESP32 → backend | `sentinelx/<table>/sensors` | `{"temp":23.4,"hum":51.2,"gas":1234}` | toutes les 5 s |
| backend → ESP32 | `sentinelx/<table>/cmd` | `{"buzzer":"on"}` ou `{"buzzer":"off"}` | sur événement |

- `temp` : °C, `hum` : % d'humidité relative, `gas` : valeur ADC brute (0 à 4095). Pas de conversion en ppm.
- Un payload invalide est ignoré et journalisé.
- Le backend s'abonne à `sentinelx/+/sensors` et reconnecte automatiquement si le broker tombe.

Test manuel depuis le PC avec Mosquitto installé :

```bash
mosquitto_sub -h localhost -t "sentinelx/#" -v
mosquitto_pub -h localhost -t "sentinelx/table1/cmd" -m '{"buzzer":"on"}'
```

## API REST

Base : `http://localhost:8000/api/v1`. Documentation interactive : http://localhost:8000/docs

| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | état du service |
| GET | `/mesures?table_id=&limit=` | dernières mesures, les plus récentes d'abord (limit max 1000) |
| GET | `/alertes?table_id=&limit=` | dernières alertes (limit max 500) |
| GET | `/tables/{table_id}/etat` | `{"alerte_active": bool, "modele_entraine": bool}` |
| POST | `/tables/{table_id}/entrainement` | entraîne le modèle sur les mesures stockées (100 minimum, 5000 maximum) |
| POST | `/tables/{table_id}/commande` | body `{"buzzer":"on"}` ou `{"buzzer":"off"}`, renvoie 202 |

Exemples :

```bash
curl "http://localhost:8000/api/v1/mesures?table_id=table1&limit=5"
curl -X POST http://localhost:8000/api/v1/tables/table1/entrainement
curl -X POST http://localhost:8000/api/v1/tables/table1/commande \
     -H "Content-Type: application/json" -d '{"buzzer":"on"}'
```

L'API n'a pas encore d'authentification. Elle est à usage local sur le WiFi de la table.

## Modèle d'IA

Le modèle ne contient aucun seuil écrit à la main. Il apprend ce qui est normal pour une table, puis signale ce qui s'en écarte.

**Entrée.** À chaque mesure, on prend les 30 dernières (environ 2,5 minutes). Cinq valeurs sont calculées :
- température, humidité et gaz de la mesure courante ;
- pente de la température et pente du gaz sur la fenêtre (tendance).

**Algorithme.** `LocalOutlierFactor` en mode nouveauté, précédé d'un `StandardScaler`, avec `n_neighbors=20` et `contamination=0.05`. Un point est une anomalie s'il se trouve dans une zone beaucoup moins dense que ses voisins appris.

**Entraînement.** `POST /tables/{table_id}/entrainement` calcule les 5 valeurs pour chaque mesure stockée, entraîne le modèle, puis l'enregistre dans `backend/models/<table>.joblib` (volume `model-data`). Le modèle est rechargé au besoin après un redémarrage.

**Détection.** Chaque mesure reçue est évaluée :
- première anomalie → une ligne dans `alerts` et une commande `buzzer on` ;
- retour à la normale → commande `buzzer off`.

Une alerte n'est créée qu'au passage en anomalie, pas à chaque mesure.

**Bonnes pratiques d'entraînement.** Entraîne sur une période normale : pas de test au gaz, pas de sortie d'humain dans le champ, et pas de simulation de pic pendant la baseline. Un pic présent dans les données d'entraînement est appris comme normal.

## Tests avec le simulateur

Sans ESP32, le simulateur publie des mesures normales toutes les 5 s, et un pic de gaz à 60 s avec `--pic`.

Le simulateur tourne dans le conteneur, car paho-mqtt n'est pas installé sur l'hôte :

```bash
docker compose exec -T backend python - --host mosquitto --pic < tools/simulate_sensors.py
```

Scénario de test :
1. Laisse tourner environ 2 minutes pour avoir plus de 100 mesures.
2. Entraîne le modèle : `POST /tables/table1/entrainement`.
3. Attends le pic à 60 s : `GET /tables/table1/etat` doit passer à `alerte_active: true`.

## Limites connues

- **Fausse alerte après un pic** : pendant que le pic sort de la fenêtre de 30 mesures, la pente change et une mesure normale peut être signalée. À corriger (par exemple : exiger plusieurs mesures normales avant de couper l'alerte).
- **État d'alerte en mémoire** : l'état actif/inactif n'est pas persisté. Après un redémarrage du backend, la prochaine mesure le recalcule.
- **Un seul modèle par table**, pas de versionnage ni de rollback.
- **Pas de migrations** : les tables sont créées avec `create_all` au démarrage. Un changement de schéma impose de supprimer le volume.
- **MQTT en clair et sans authentification** : Mosquitto accepte les connexions anonymes sur le port 1883. Le sujet exige MQTTS (TLS) et des identifiants.
- **API sans authentification.**
- **Pas encore de firmware ESP32 dans ce dépôt** : le contrat de données ci-dessus est la seule interface attendue.
- **Pas encore de module vision (webcam)** : il est écarté pour l'instant.
- **Frontend** : une seule table codée en dur (`table1`) dans `App.jsx`. Pas encore de conteneur Docker pour le frontend.

## Feuille de route

1. Firmware ESP32 (lecture des capteurs, publication, buzzer).
2. TLS sur MQTT et authentification du broker.
3. Authentification de l'API, migrations Alembic.
4. Correction de la fausse alerte post-pic.
5. Sélection de la table dans le frontend, conteneur Docker du frontend.
6. Module vision (webcam) si retenu.
