from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_password: str = ""
    gmail_user: str = ""
    gmail_app_password: str = ""
    alert_to: str = ""
    media_dir: str = "media"
    # Rétention (MCO) : au-delà, les données sont purgées toutes les heures
    retention_mesures_jours: int = 7
    retention_clips_jours: int = 3
    media_max_mo: int = 500
    # Authentification de l'API (valeurs générées par lancer.ps1 dans le .env)
    admin_user: str = "admin"
    admin_password: str = ""
    jwt_secret: str = ""
    jwt_duree_heures: int = 8


settings = Settings()
