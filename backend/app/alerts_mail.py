import base64
from datetime import datetime
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from app.config import settings

PARIS = ZoneInfo("Europe/Paris")

NAVY = "#0f2236"
ALERT = "#c0392b"
INK = "#1d2630"
MUTED = "#6b7b88"
LINE = "#e3e9ee"
PAGE = "#f2f5f8"


def _maintenant() -> datetime:
    return datetime.now(PARIS)


def _date(moment: datetime) -> str:
    return moment.strftime("%d/%m/%Y à %H:%M")


def _phrase_causale(details: dict | None) -> str:
    if not details or not details.get("caracteristiques"):
        return ""
    avec_ecart = [c for c in details["caracteristiques"] if c.get("ecart") is not None]
    if not avec_ecart:
        return ""
    pire = max(avec_ecart, key=lambda c: abs(c["ecart"]))
    sens = "au-dessus" if pire["ecart"] > 0 else "en dessous"
    return (
        f'<div style="font-size:13px;color:{INK};margin:4px 0 16px;line-height:1.5;">'
        f'Surtout causée par <b>{pire["nom"]}</b> : {pire["valeur"]} contre {pire.get("normal", "—")} habituellement, '
        f'soit {abs(pire["ecart"])} σ {sens} de la normale.</div>'
    )


def _tableau_caracteristiques(details: dict | None) -> str:
    if not details or not details.get("caracteristiques"):
        return ""
    lignes = ""
    for c in details["caracteristiques"]:
        ecart = c.get("ecart")
        hors_norme = ecart is not None and abs(ecart) > 3
        couleur = f"color:{ALERT};font-weight:bold;" if hors_norme else ""
        ecart_txt = f"{ecart} σ" if ecart is not None else "—"
        lignes += (
            f'<tr><td style="padding:6px 8px;border-bottom:1px solid {LINE};font-size:12px;">{c["nom"]}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid {LINE};font-size:12px;{couleur}">{c["valeur"]}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid {LINE};font-size:12px;color:{MUTED};">{c.get("normal", "—")}</td>'
            f'<td style="padding:6px 8px;border-bottom:1px solid {LINE};font-size:12px;{couleur}">{ecart_txt}</td></tr>'
        )
    modele = details.get("modele", "")
    facteur = details.get("facteur_lof")
    sous = f" · facteur LOF {facteur} (normal ≈ 1)" if facteur is not None else ""
    return (
        f'<div style="font-size:11px;letter-spacing:0.06em;text-transform:uppercase;color:{MUTED};margin:20px 0 8px;">'
        f"Comment c'est détecté — modèle {modele}{sous}</div>"
        f'<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="border-collapse:collapse;">'
        f'<tr><th style="text-align:left;padding:6px 8px;border-bottom:2px solid {LINE};font-size:11px;color:{MUTED};">Caractéristique</th>'
        f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid {LINE};font-size:11px;color:{MUTED};">Valeur</th>'
        f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid {LINE};font-size:11px;color:{MUTED};">Normal</th>'
        f'<th style="text-align:left;padding:6px 8px;border-bottom:2px solid {LINE};font-size:11px;color:{MUTED};">Écart</th></tr>'
        f"{lignes}</table>"
    )


def _tuile(libelle: str, valeur: str) -> str:
    return (
        f'<td style="width:33%;padding:14px 12px;background:#f8fafb;border:1px solid {LINE};'
        f'text-align:center;font-family:Arial,Helvetica,sans-serif;">'
        f'<div style="font-size:11px;letter-spacing:0.08em;text-transform:uppercase;color:{MUTED};">{libelle}</div>'
        f'<div style="font-size:22px;font-weight:bold;color:{INK};margin-top:4px;">{valeur}</div>'
        "</td>"
    )


def _enveloppe(titre: str, sous_titre: str, corps: str, pied_photo: str = "") -> str:
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:{PAGE};">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:{PAGE};padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width:560px;width:100%;background:#ffffff;border:1px solid {LINE};">
  <tr><td style="background:{NAVY};border-top:4px solid {ALERT};padding:22px 26px;font-family:Arial,Helvetica,sans-serif;">
    <div style="font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:#8fa8bd;">SENTINEL-X · Supervision</div>
    <div style="font-size:24px;font-weight:bold;color:#ffffff;margin-top:6px;">{titre}</div>
    <div style="font-size:13px;color:#b9c9d6;margin-top:4px;">{sous_titre}</div>
  </td></tr>
  <tr><td style="padding:24px 26px;font-family:Arial,Helvetica,sans-serif;color:{INK};">
    {corps}
  </td></tr>
  {pied_photo}
  <tr><td style="padding:14px 26px;background:#f8fafb;border-top:1px solid {LINE};font-family:Arial,Helvetica,sans-serif;font-size:11px;color:{MUTED};">
    Message automatique envoyé par le système de surveillance. Au plus un mail toutes les 5 minutes.
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def mail_anomalie(
    table_id: str, temp: float, hum: float, gas: int, details: dict | None = None
) -> EmailMessage:
    moment = _maintenant()
    corps = f"""
    <div style="font-size:15px;line-height:1.5;margin-bottom:18px;">
      Les capteurs <b>{table_id}</b> ont relevé un comportement anormal, le <b>{_date(moment)}</b>.
    </div>
    <table role="presentation" width="100%" cellspacing="8" cellpadding="0">
      <tr>{_tuile("Température", f"{temp:.1f} °C")}{_tuile("Humidité", f"{hum:.1f} %")}{_tuile("Gaz (ADC)", str(gas))}</tr>
    </table>
    {_phrase_causale(details)}
    {_tableau_caracteristiques(details)}
    <div style="font-size:13px;color:{MUTED};margin-top:16px;line-height:1.5;">
      L'alarme sonore de la table est activée. Elle se coupe automatiquement quand les mesures redeviennent normales.
    </div>"""
    html = _enveloppe("Anomalie capteurs", _date(moment), corps)
    lignes_texte = ""
    if details and details.get("caracteristiques"):
        lignes_texte = "\nDétail :\n" + "\n".join(
            f"- {c['nom']} : {c['valeur']} (normal {c.get('normal', '—')}"
            + (f", écart {c['ecart']} σ)" if c.get("ecart") is not None else ")")
            for c in details["caracteristiques"]
        ) + "\n"
    texte = (
        f"ANOMALIE CAPTEURS · table {table_id}\n"
        f"Date : {_date(moment)}\n\n"
        f"Température : {temp:.1f} °C\nHumidité : {hum:.1f} %\nGaz (ADC) : {gas}\n"
        f"{lignes_texte}\n"
        "L'alarme sonore est activée. Elle se coupe quand les mesures redeviennent normales.\n"
    )
    return _composer(f"[SENTINEL-X] Anomalie capteurs · table {table_id}", texte, html)


def mail_hausse(
    table_id: str, temp: float, probabilite: float, details: dict | None = None
) -> EmailMessage:
    moment = _maintenant()
    pourcentage = round(probabilite * 100)
    corps = f"""
    <div style="font-size:15px;line-height:1.5;margin-bottom:18px;">
      La température des capteurs <b>{table_id}</b> monte de façon continue, le <b>{_date(moment)}</b>.
    </div>
    <table role="presentation" width="100%" cellspacing="8" cellpadding="0">
      <tr>{_tuile("Température actuelle", f"{temp:.1f} °C")}{_tuile("Probabilité de hausse", f"{pourcentage} %")}</tr>
    </table>
    <div style="margin:16px 0 4px;font-size:12px;color:{MUTED};">Niveau de confiance du modèle</div>
    <div style="background:{LINE};height:8px;width:100%;">
      <div style="background:#f5b041;height:8px;width:{max(1, min(100, pourcentage))}%;"></div>
    </div>
    {_tableau_caracteristiques(details)}
    <div style="font-size:13px;color:{MUTED};margin-top:16px;line-height:1.5;">
      Ce n'est pas un seuil : le modèle a reconnu une tendance à la hausse sur les dernières minutes.
    </div>"""
    html = _enveloppe("Hausse de température", _date(moment), corps)
    lignes_texte = ""
    if details and details.get("caracteristiques"):
        lignes_texte = "\nDétail :\n" + "\n".join(
            f"- {c['nom']} : {c['valeur']} (référence {c.get('normal', '—')})"
            for c in details["caracteristiques"]
        ) + "\n"
    texte = (
        f"HAUSSE DE TEMPÉRATURE · table {table_id}\n"
        f"Date : {_date(moment)}\nTempérature actuelle : {temp:.1f} °C\n"
        f"Probabilité de hausse : {pourcentage} %\n"
        f"{lignes_texte}\n"
        "Le modèle a reconnu une tendance à la hausse sur les dernières minutes.\n"
    )
    return _composer(f"[SENTINEL-X] Hausse de température · table {table_id}", texte, html)


LIMITE_PIECES_JOINTES = 20 * 1024 * 1024


def mail_personne(
    table_id: str,
    confiance: float,
    image: bytes | None,
    clip: bytes | None = None,
) -> EmailMessage:
    moment = _maintenant()
    pourcentage = round(confiance * 100)
    largeur = max(1, min(100, pourcentage))
    taille_pieces = len(image or b"") + len(clip or b"")
    clip_joint = clip is not None and taille_pieces <= LIMITE_PIECES_JOINTES
    photo_bloc = ""
    if image is not None:
        photo_bloc = f"""
    <div style="font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:{MUTED};margin:22px 0 8px;">Capture au moment de la détection</div>
    <img src="cid:photo" alt="Capture de la webcam" width="508" style="display:block;width:100%;max-width:508px;height:auto;border:1px solid {LINE};">
    <div style="font-size:12px;color:{MUTED};margin-top:6px;">Capture jointe au mail (capture.jpg){' · vidéo de 10 secondes jointe (sentinel-clip.mp4)' if clip_joint else ''}.</div>"""
    corps = f"""
    <div style="font-size:15px;line-height:1.5;margin-bottom:18px;">
      Une personne a été détectée devant la caméra <b>{table_id}</b>, le <b>{_date(moment)}</b>.
    </div>
    <table role="presentation" width="100%" cellspacing="8" cellpadding="0">
      <tr>{_tuile("Table", table_id)}{_tuile("Confiance", f"{pourcentage} %")}{_tuile("Heure", moment.strftime("%H:%M"))}</tr>
    </table>
    <div style="margin:16px 0 4px;font-size:12px;color:{MUTED};">Niveau de confiance</div>
    <div style="background:{LINE};height:8px;width:100%;">
      <div style="background:{ALERT};height:8px;width:{largeur}%;"></div>
    </div>
    {photo_bloc}"""
    html = _enveloppe("Personne détectée", _date(moment), corps)
    texte = (
        f"PERSONNE DÉTECTÉE · table {table_id}\n"
        f"Date : {_date(moment)}\nConfiance : {pourcentage} %\n"
        + ("La capture de la webcam est jointe.\n" if image is not None else "")
        + ("La vidéo de 10 secondes est jointe.\n" if clip_joint else "")
    )
    msg = _composer(f"[SENTINEL-X] Personne détectée · table {table_id}", texte, html)
    if image is not None:
        msg.get_body(preferencelist=("html",)).add_related(
            image, maintype="image", subtype="jpeg", cid="<photo>"
        )
        msg.add_attachment(image, maintype="image", subtype="jpeg", filename="capture.jpg")
    if clip_joint:
        msg.add_attachment(clip, maintype="video", subtype="mp4", filename="sentinel-clip.mp4")
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
