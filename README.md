# Workshop MELTY : SENTINEL-X

Supervision météo et sécurité d'une table : un ESP32 relève température, humidité et gaz, un modèle d'IA détecte les anomalies, et un dashboard affiche l'état en temps réel.

## Stack

- **Backend** : Python, FastAPI, SQLAlchemy, PostgreSQL, paho-mqtt
- **Broker** : Mosquitto (MQTT)
- **Frontend** : React (Vite)
- **Infra** : Docker Compose

## Lancer le backend

```bash
cp .env.example .env
docker compose up --build
```

L'API répond sur `http://localhost:8000/health`.
