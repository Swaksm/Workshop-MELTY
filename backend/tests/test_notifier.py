import pytest

from app import alerts_mail
from app import notifier as notifier_module
from app.notifier import Notifier


@pytest.fixture
def mail_configure(monkeypatch):
    monkeypatch.setattr(notifier_module.settings, "gmail_user", "workshopmelty@gmail.com")
    monkeypatch.setattr(notifier_module.settings, "gmail_app_password", "secret")
    monkeypatch.setattr(notifier_module.settings, "alert_to", "workshopmelty@gmail.com")


def test_pas_plus_d_un_mail_toutes_les_5_minutes(mail_configure, monkeypatch):
    n = Notifier()
    envois = []
    monkeypatch.setattr(n, "_lancer", lambda msg: envois.append(msg))

    assert n.anomalie("table1", 23.1, 50.2, 3500) is True
    assert n.anomalie("table1", 23.1, 50.2, 3600) is False
    assert n.personne("table1", 0.9, None, None) is False
    assert len(envois) == 1


def test_aucun_mail_sans_configuration(monkeypatch):
    monkeypatch.setattr(notifier_module.settings, "gmail_user", "")
    monkeypatch.setattr(notifier_module.settings, "gmail_app_password", "")
    monkeypatch.setattr(notifier_module.settings, "alert_to", "")
    assert Notifier().anomalie("table1", 23.1, 50.2, 3500) is False


def test_mail_personne_contient_la_photo(mail_configure):
    image = b"\xff\xd8\xff\xd9"
    msg = alerts_mail.mail_personne("table1", 0.91, image)

    html = msg.get_body(preferencelist=("html",)).get_content()
    assert "Personne détectée" in html
    assert "cid:photo" in html
    assert any(part.get("Content-ID") == "<photo>" for part in msg.walk())
    assert msg["To"] == "workshopmelty@gmail.com"


def test_mail_personne_joint_la_video(mail_configure):
    msg = alerts_mail.mail_personne("table1", 0.9, b"\xff\xd8\xff\xd9", b"fake-mp4")

    parties = [p for p in msg.walk() if p.get_content_type() == "video/mp4"]
    assert len(parties) == 1
    assert parties[0].get_filename() == "sentinel-clip.mp4"


def test_video_ecartee_si_le_mail_depasse_la_limite(mail_configure, monkeypatch):
    monkeypatch.setattr(alerts_mail, "LIMITE_PIECES_JOINTES", 10)
    msg = alerts_mail.mail_personne("table1", 0.9, b"\xff\xd8\xff\xd9", b"x" * 100)

    assert not [p for p in msg.walk() if p.get_content_type() == "video/mp4"]


def test_mail_anomalie_recapitule_les_valeurs(mail_configure):
    msg = alerts_mail.mail_anomalie("table1", 23.1, 50.2, 3500)

    texte = msg.get_body(preferencelist=("plain",)).get_content()
    assert "23.1 °C" in texte
    assert "50.2 %" in texte
    assert "3500" in texte
    assert "cid:photo" not in msg.get_body(preferencelist=("html",)).get_content()
