import base64
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from app.config import settings

PARIS = ZoneInfo("Europe/Paris")
CSS = """
body { margin: 0; background: #f3f6f9; font-family: Arial, Helvetica, sans-serif; color: #1d2630; }
.card { max-width: 560px; margin: 24px auto; background: #ffffff; border: 1px solid #d5dde4; }
.bar { padding: 18px 22px; color: #ffffff; }
.bar.alert { background: #c0392b; }
.bar.info { background: #0f5c7a; }
.bar h1 { margin: 0; font-size: 18px; letter-spacing: 0.02em; }
.bar p { margin: 4px 0 0; font-size: 13px; opacity: 0.9; }
.body { padding: 18px 22px; }
table { width: 100%; border-collapse: collapse; font-size: 14px; }
td { padding: 8px 0; border-bottom: 1px solid #eef2f5; }
td.k { color: #6b7b88; width: 42%; }
td.v { font-weight: 600; }
.photo { margin-top: 16px; }
.photo img { width: 100%; display: block; border: 1px solid #d5dde4; }
.foot { padding: 14px 22px; font-size: 12px; color: #6b7b88; background: #f8fafb; }
"""


def _maintenant() -> str:
    return datetime.now(PARIS).strftime("%d/%m/%Y à %H:%M:%S")


def _html(bar_class: str, titre: str, sous_titre: str, lignes: list[tuple[str, str]], photo: bool) -> str:
    rows = "".join(f'<tr><td class="k">{k}</td><td class="v">{v}</td></tr>' for k, v in lignes)
    bloc_photo = (
        '<div class="photo"><img src="cid:photo" alt="Capture de la webcam"></div>' if photo else ""
    )
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><div class="card">
<div class="bar {bar_class}"><h1>{titre}</h1><p>{sous_titre}</p></div>
<div class="body"><table>{rows}</table>{bloc_photo}</div>
<div class="foot">SENTINEL-X · Message automatique, ne pas répondre.</div>
</div></body></html>"""


def mail_anomalie(table_id: str, temp: float, hum: float, gas: int) -> EmailMessage:
    maintenant = _maintenant()
    lignes = [
        ("Table", table_id),
        ("Heure", maintenant),
        ("Température", f"{temp:.1f} °C"),
        ("Humidité", f"{hum:.1f} %"),
        ("Gaz (ADC)", str(gas)),
    ]
    texte = (
        f"Anomalie détectée sur {table_id} le {maintenant}.\n"
        f"Température : {temp:.1f} °C\nHumidité : {hum:.1f} %\nGaz (ADC) : {gas}\n"
    )
    html = _html("alert", "Anomalie détectée", f"Table {table_id}", lignes, photo=False)
    return _composer(f"[SENTINEL-X] Anomalie capteurs · {table_id}", texte, html)


def mail_personne(table_id: str, confiance: float, image: bytes | None) -> EmailMessage:
    maintenant = _maintenant()
    lignes = [
        ("Table", table_id),
        ("Heure", maintenant),
        ("Détection", "Personne"),
        ("Confiance", f"{confiance:.0%}"),
    ]
    texte = (
        f"Personne détectée sur {table_id} le {maintenant} (confiance {confiance:.0%}).\n"
        "La capture de la webcam est jointe.\n"
    )
    html = _html("alert", "Personne détectée", f"Webcam · table {table_id}", lignes, photo=image is not None)
    msg = _composer(f"[SENTINEL-X] Personne détectée · {table_id}", texte, html)
    if image is not None:
        msg.get_body(preferencelist=("html",)).add_related(
            image, maintype="image", subtype="jpeg", cid="<photo>"
        )
    return msg


def _composer(sujet: str, texte: str, html: str) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = sujet
    msg["From"] = settings.gmail_user
    msg["To"] = settings.alert_to
    msg.set_content(texte)
    msg.add_alternative(html, subtype="html")
    return msg


def decoder_image(texte_base64: str | None) -> bytes | None:
    if not texte_base64:
        return None
    return base64.b64decode(texte_base64)
