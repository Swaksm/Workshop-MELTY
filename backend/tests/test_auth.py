from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import auth, main

MDP = "mot-de-passe-de-test"


@pytest.fixture
def client(monkeypatch):
    main.app.dependency_overrides.clear()  # vraie authentification
    monkeypatch.setattr(auth.settings, "admin_password", MDP)
    return TestClient(main.app, base_url="https://testserver")


def connexion(client, mdp=MDP):
    return client.post("/api/v1/auth/login", json={"utilisateur": "admin", "mot_de_passe": mdp})


@pytest.mark.parametrize(
    "methode, route",
    [
        ("get", "/api/v1/mesures"),
        ("get", "/api/v1/supervision"),
        ("get", "/api/v1/tables/table1/etat"),
        ("post", "/api/v1/tables/table1/commande"),
        ("post", "/api/v1/tables/table1/entrainement"),
    ],
)
def test_routes_refusees_sans_jeton(client, methode, route):
    r = getattr(client, methode)(route)
    assert r.status_code == 401


def test_health_reste_public(client):
    assert client.get("/health").status_code == 200


def test_connexion_pose_un_cookie_securise(client):
    r = connexion(client)
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=strict" in cookie
    assert client.get("/api/v1/mesures").status_code == 200  # cookie renvoyé
    assert client.get("/api/v1/auth/verifier").status_code == 204


def test_jeton_bearer(client):
    token = connexion(client).json()["token"]
    client.cookies.clear()
    r = client.get("/api/v1/mesures", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200


def test_mauvais_mot_de_passe(client):
    assert connexion(client, "faux").status_code == 401
    assert client.get("/api/v1/auth/verifier").status_code == 401


def test_jeton_falsifie_ou_expire(client):
    vieux, _ = auth.creer_token("admin", datetime.now(timezone.utc) - timedelta(days=2))
    for token in (vieux, "abc.def.ghi"):
        r = client.get("/api/v1/mesures", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 401


def test_blocage_apres_trop_d_echecs(client):
    for _ in range(auth.MAX_ECHECS):
        assert connexion(client, "faux").status_code == 401
    assert connexion(client).status_code == 429  # même le bon mot de passe est bloqué


@pytest.mark.parametrize("valeur", ["", "change-me"])
def test_mot_de_passe_absent_ou_d_exemple_refuse(client, monkeypatch, valeur):
    monkeypatch.setattr(auth.settings, "admin_password", valeur)
    assert connexion(client, valeur).status_code == 401


def test_deconnexion_efface_le_cookie(client):
    connexion(client)
    client.post("/api/v1/auth/logout")
    assert client.get("/api/v1/mesures").status_code == 401
