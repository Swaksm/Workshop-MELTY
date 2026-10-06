from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    mqtt_host: str = "mosquitto"
    mqtt_port: int = 1883
    gmail_user: str = ""
    gmail_app_password: str = ""
    alert_to: str = ""


settings = Settings()
