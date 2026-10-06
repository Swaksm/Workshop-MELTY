import logging
import smtplib
import threading
import time

from email.message import EmailMessage

from app.alerts_mail import mail_anomalie, mail_hausse, mail_personne
from app.config import settings

log = logging.getLogger(__name__)

MIN_INTERVAL_SECONDS = 300.0
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


class Notifier:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._dernier_envoi: dict[str, float] = {}

    def configuree(self) -> bool:
        return bool(settings.gmail_user and settings.gmail_app_password and settings.alert_to)

    def _autorise(self, kind: str) -> bool:
        with self._lock:
            maintenant = time.monotonic()
            dernier = self._dernier_envoi.get(kind)
            if dernier is not None and maintenant - dernier < MIN_INTERVAL_SECONDS:
                return False
            self._dernier_envoi[kind] = maintenant
            return True

    def _envoyer(self, msg: EmailMessage) -> None:
        try:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
                smtp.starttls()
                smtp.login(settings.gmail_user, settings.gmail_app_password)
                smtp.send_message(msg)
            log.info("Mail envoyé : %s", msg["Subject"])
        except (smtplib.SMTPException, OSError):
            log.exception("Échec de l'envoi du mail")

    def _publier(self, kind: str, construire) -> bool:
        if not self.configuree():
            log.warning("Envoi de mail désactivé : GMAIL_USER, GMAIL_APP_PASSWORD ou ALERT_TO manquant")
            return False
        if not self._autorise(kind):
            log.info("Mail '%s' non envoyé : un mail de ce type a déjà été envoyé il y a moins de 5 minutes", kind)
            return False
        self._lancer(construire())
        return True

    def _lancer(self, msg: EmailMessage) -> None:
        threading.Thread(target=self._envoyer, args=(msg,), daemon=True).start()

    def anomalie(self, table_id: str, temp: float, hum: float, gas: int) -> bool:
        return self._publier("anomalie", lambda: mail_anomalie(table_id, temp, hum, gas))

    def hausse(self, table_id: str, temp: float, probabilite: float) -> bool:
        return self._publier("hausse", lambda: mail_hausse(table_id, temp, probabilite))

    def personne(
        self,
        table_id: str,
        confiance: float,
        image: bytes | None,
        clip: bytes | None,
    ) -> bool:
        return self._publier("personne", lambda: mail_personne(table_id, confiance, image, clip))


notifier = Notifier()
