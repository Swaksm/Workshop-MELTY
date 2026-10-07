"""Authentification de l'API : connexion par identifiant/mot de passe, jeton JWT.

Le jeton est posé dans un cookie HttpOnly (illisible par le JavaScript de la page,
envoyé automatiquement par le navigateur, y compris pour le flux vidéo) et renvoyé
dans la réponse pour les scripts, qui l'envoient en `Authorization: Bearer`.
"""

import hmac
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from app.config import settings

COOKIE = "sentinelx_token"
ALGORITHME = "HS256"
# Anti-force brute : au-delà de 10 échecs en une minute, connexion refusée (429).
# Sous Docker Desktop, tous les clients arrivent avec la même adresse (NAT de
# Docker) : un blocage long permettrait à un attaquant de bloquer toute l'équipe,
# d'où une fenêtre courte. Le mot de passe (24 caractères aléatoires) reste la
# vraie protection.
MAX_ECHECS = 10
FENETRE_ECHECS_S = 60

# Sans JWT_SECRET dans le .env, une clé aléatoire est tirée au démarrage :
# les jetons ne survivent alors pas à un redémarrage du backend.
VALEURS_EXEMPLE = {"", "change-me"}  # valeurs de .env.example : jamais acceptées
_cle = settings.jwt_secret if settings.jwt_secret not in VALEURS_EXEMPLE else secrets.token_urlsafe(32)
_echecs: dict[str, list[float]] = {}
_echecs_lock = threading.Lock()

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class ConnexionIn(BaseModel):
    utilisateur: str
    mot_de_passe: str


class ConnexionOut(BaseModel):
    utilisateur: str
    token: str
    expire: datetime


def creer_token(utilisateur: str, maintenant: datetime | None = None) -> tuple[str, datetime]:
    maintenant = maintenant or datetime.now(timezone.utc)
    expire = maintenant + timedelta(hours=settings.jwt_duree_heures)
    token = jwt.encode({"sub": utilisateur, "iat": maintenant, "exp": expire}, _cle, algorithm=ALGORITHME)
    return token, expire


def _lire_token(request: Request) -> str | None:
    entete = request.headers.get("authorization", "")
    if entete.lower().startswith("bearer "):
        return entete[7:].strip()
    return request.cookies.get(COOKIE)


def exiger_auth(request: Request) -> str:
    """Dépendance FastAPI des routes protégées : renvoie l'utilisateur ou 401."""
    token = _lire_token(request)
    if token:
        try:
            return jwt.decode(token, _cle, algorithms=[ALGORITHME])["sub"]
        except jwt.PyJWTError:
            pass
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentification requise",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _ip_client(request: Request) -> str:
    # L'API n'est joignable que par le reverse proxy et la boucle locale :
    # X-Forwarded-For vient donc de Caddy, pas d'un client qui le forgerait.
    transmis = request.headers.get("x-forwarded-for")
    if transmis:
        return transmis.split(",")[0].strip()
    return request.client.host if request.client else "inconnu"


def _trop_d_echecs(ip: str, maintenant: float) -> bool:
    with _echecs_lock:
        recents = [t for t in _echecs.get(ip, []) if maintenant - t < FENETRE_ECHECS_S]
        _echecs[ip] = recents
        return len(recents) >= MAX_ECHECS


def _noter_echec(ip: str, maintenant: float) -> None:
    with _echecs_lock:
        _echecs.setdefault(ip, []).append(maintenant)


def _identifiants_valides(utilisateur: str, mot_de_passe: str) -> bool:
    if settings.admin_password in VALEURS_EXEMPLE:
        return False  # pas de vrai mot de passe configuré : personne ne se connecte
    ok_user = hmac.compare_digest(utilisateur.encode(), settings.admin_user.encode())
    ok_mdp = hmac.compare_digest(mot_de_passe.encode(), settings.admin_password.encode())
    return ok_user and ok_mdp


@router.post("/login", response_model=ConnexionOut)
def login(body: ConnexionIn, request: Request, response: Response) -> ConnexionOut:
    ip = _ip_client(request)
    maintenant = time.monotonic()
    if _trop_d_echecs(ip, maintenant):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Trop de tentatives, réessayer dans quelques minutes",
        )
    if not _identifiants_valides(body.utilisateur, body.mot_de_passe):
        _noter_echec(ip, maintenant)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Identifiant ou mot de passe incorrect")

    token, expire = creer_token(body.utilisateur)
    response.set_cookie(
        COOKIE,
        token,
        max_age=settings.jwt_duree_heures * 3600,
        httponly=True,
        secure=True,  # les navigateurs l'acceptent aussi sur http://localhost (dev)
        samesite="strict",  # protège les POST (commande, entraînement) contre le CSRF
        path="/",
    )
    return ConnexionOut(utilisateur=body.utilisateur, token=token, expire=expire)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(COOKIE, path="/", secure=True, httponly=True, samesite="strict")


@router.get("/verifier", status_code=status.HTTP_204_NO_CONTENT)
def verifier(request: Request) -> None:
    """Utilisée par Caddy (forward_auth) avant de laisser passer vers le module vision."""
    exiger_auth(request)
