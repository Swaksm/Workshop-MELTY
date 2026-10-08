# Sécurité — SENTINEL-X (groupe 9)

Document destiné au dossier technique : surface d'attaque, matrice de sécurité
(menace → mesure → preuve → risque résiduel) et protocole de preuves pour la soutenance. Réseau et flux : voir [reseau.md](reseau.md).

## 1. Surface d'attaque

Depuis le Wi-Fi de l'école (le réseau partagé avec les autres groupes), il n'y a que
**deux portes**, toutes deux chiffrées :

| Port | Service | Chiffrement | Authentification |
|---|---|---|---|
| 8883 | MQTT (ESP32 → broker) | TLS 1.2 minimum, TLS mutuel, certificats signés par la CA du projet | **certificat client de l'ESP32**, puis compte par appareil + ACL |
| 443 | HTTPS (dashboard, API, flux vidéo) via le reverse proxy Caddy | TLS 1.2 / 1.3, même CA | **certificat client du poste** (5 postes autorisés), puis connexion au dashboard et jeton JWT |

Tout le reste n'écoute que sur la boucle locale du PC (`127.0.0.1`) ou sur le réseau Docker
interne : MQTT en clair (1883), API directe (8000), module vision (8001), dashboard de
développement (5173), cAdvisor (8080), PostgreSQL (5432, aucun port publié).

```
  Wi-Fi école ──► :8883  Mosquitto (TLS mutuel, comptes, ACL) ──► backend ──► PostgreSQL
              └─► :443   Caddy (TLS + certificat du poste exigé)
                            │
                            ├─ /api/*     ──► backend (vérifie le jeton)
                            ├─ /vision/*  ──► vérif. session ──► module vision
                            └─ /          ──► dashboard compilé
```

## 2. Matrice de sécurité

| # | Menace | Mesure prise | Preuve | Risque résiduel |
|---|---|---|---|---|
| M1 | **Écoute du réseau** (Wireshark sur le Wi-Fi partagé) : lecture des mesures, des mots de passe MQTT | MQTT de l'ESP32 en TLS (8883). Dashboard, API et vidéo en HTTPS (443). Le MQTT en clair (1883) n'est pas publié sur le Wi-Fi | capture Wireshark sur 8883 (seulement « Application Data » TLS) comparée à une capture locale du 1883 (topics et JSON lisibles) ; `nmap` : 1883 fermé depuis le Wi-Fi | le trafic local (vision → 1883, backend → base) reste en clair, mais il ne quitte pas la machine |
| M2 | **Homme du milieu** (faux broker, usurpation ARP) | l'ESP32 vérifie le certificat du broker avec la CA du projet (`setCACert`) ; le certificat contient l'IP du serveur (CN et SAN). Le navigateur vérifie le certificat HTTPS | `openssl s_client -verify_ip` : OK avec la bonne IP, « IP address mismatch » avec une autre ; un faux serveur sans la clé de la CA est refusé | si la clé de la CA (`ca.key`) était volée, un faux serveur serait possible : elle ne quitte pas le PC et n'est jamais commitée |
| M3 | **Broker ouvert** : un inconnu publie de fausses mesures ou déclenche le buzzer | TLS mutuel sur 8883 : le client doit présenter un certificat signé par la CA (`clients/esp32.crt`), sinon la connexion est coupée avant toute authentification ; puis `allow_anonymous false`, un compte par composant (`backend`, `vision`, `esp32`), mots de passe aléatoires générés par `lancer.ps1` | connexion sans certificat client, ou avec `server.crt` → coupée par le broker ; `mosquitto_sub` anonyme → « not authorised » ; mauvais mot de passe → refus ; vérification automatique dans la CI | Mosquitto accepte tout certificat client signé par la CA : un certificat de poste associé au mot de passe `esp32` passerait (il faut deux secrets de l'équipe). Le vol du boîtier donne accès au certificat, à la clé et au mot de passe stockés dans la flash de l'ESP32 : ils permettent de publier des mesures, dans la limite des ACL (révocation : supprimer `clients/esp32.*`, relancer, reflasher). Sous Docker Desktop, `passwd` et `acl` montés depuis Windows ne peuvent pas appartenir à l'utilisateur `mosquitto` en mode 600 (avertissement au démarrage) : les mots de passe y sont hachés |
| M4 | **Abus d'un compte MQTT** : le compte de l'ESP32 lit la vidéo ou envoie des commandes | ACL : chaque compte ne lit ou n'écrit que ses topics (`esp32` écrit `sensors`, lit `cmd` ; `vision` écrit `vision`) | publication refusée hors ACL (le message n'arrive pas au backend) | — |
| M5 | **Accès au dashboard par un autre groupe** (n'importe qui sur le Wi-Fi de l'école peut ouvrir `https://<IP>`) | TLS mutuel : le proxy exige un certificat client, et n'accepte que ceux des postes autorisés (`clients/autorises.pem`, 5 postes). Sans certificat valide, la connexion TLS est coupée avant même la page de connexion | navigateur sans certificat : `ERR_BAD_SSL_CLIENT_AUTH_CERT` ; certificat signé par la CA mais non listé, ou `server.crt` présenté comme client : refusé ; vérification automatique dans la CI | un poste dont le fichier `.p12` et son mot de passe sont volés est accepté jusqu'à sa révocation (supprimer `posteN.crt` puis relancer) |
| M6 | **API ouverte** : n'importe qui déclenche le buzzer, la LED, l'entraînement, lit les données | toutes les routes `/api/v1` exigent un jeton JWT signé (HS256, 8 h). Le jeton est dans un cookie HttpOnly, Secure, SameSite=Strict. L'API directe (8000) n'est publiée que sur `127.0.0.1` | `curl` sans jeton → 401 sur `/mesures`, `/commande`, `/entrainement` ; 14 tests automatiques (`test_auth.py`) et vérification dans la CI | un seul compte (`admin`) partagé par l'équipe, sans rôles |
| M7 | **Connexion au dashboard truquée** : avant, `admin/admin` était vérifié dans le navigateur (contournable) | vérification côté serveur ; mot de passe de 24 caractères aléatoires généré par `lancer.ps1` (générateur cryptographique), comparaison en temps constant | `admin/admin` refusé ; sans cookie valide, l'API renvoie 401 même si l'on force l'affichage du dashboard | — |
| M8 | **Force brute du mot de passe** | 10 échecs par minute maximum, puis 429 ; mot de passe long et aléatoire | 11ᵉ tentative en une minute → 429 | sous Docker Desktop, tous les clients ont la même adresse (NAT) : le blocage est commun à tous, d'où une fenêtre courte. Un attaquant peut gêner les connexions pendant une minute |
| M9 | **Flux vidéo espionné** : le module vision écoutait sur toutes les interfaces, sans authentification | il n'écoute plus que sur `127.0.0.1`. Depuis le réseau, `/vision/*` passe par Caddy, qui demande au backend si la session est valide (`forward_auth`) | `https://<IP>/vision/stream` sans session → 401 ; port 8001 fermé depuis le Wi-Fi | sur le PC lui-même, `127.0.0.1:8001` reste sans authentification (accès physique ou session Windows requis) |
| M10 | **CSRF / clickjacking** : une page piégée fait agir le navigateur connecté | cookie SameSite=Strict, `X-Frame-Options: DENY`, CSP `frame-ancestors 'none'` | en-têtes visibles avec `curl -I` | — |
| M11 | **Injection de payloads** (JSON malformé, valeurs aberrantes, SQL) | schémas Pydantic stricts sur MQTT et API (payload invalide ignoré et journalisé), requêtes SQLAlchemy paramétrées, taille des messages MQTT limitée à 1 Mo | payload invalide sur `sensors` → « Payload invalide », rien en base | des valeurs plausibles mais fausses (publiées avec un compte volé) faussent le modèle d'IA |
| M12 | **Déni de service** (inondation MQTT ou HTTP) | Mosquitto : 10 connexions max sur 8883, paquets de 1 Mo max, files bornées ; limites mémoire par conteneur ; redémarrage automatique | paquet de 2 Mo → « disconnected: oversize packet » dans les logs du broker ; `docker stats` stable pendant un flood ; conteneurs relancés (`restart: unless-stopped`) | sur un Wi-Fi partagé, saturer la radio ou les 10 connexions reste possible : c'est la limite principale du choix du Wi-Fi de l'école (voir reseau.md, réseau dédié) |
| M13 | **Élévation de privilèges depuis un conteneur compromis** | tous les conteneurs : `cap_drop: ALL` (la base ne récupère que 5 capacités pour son initialisation), `no-new-privileges`, `mem_limit`. Backend, broker et proxy : utilisateur non-root et système de fichiers en lecture seule. PostgreSQL : processus sous l'utilisateur `postgres` (uid 999), aucun port publié. cAdvisor : root (lecture des métriques du noyau) mais sans aucune capacité et en lecture seule | `docker inspect` (User, CapDrop, ReadonlyRootfs) ; `docker compose exec backend id` → uid 10001 | cAdvisor monte le socket containerd en lecture seule : compromis, il pourrait agir sur les conteneurs. Interface sur `127.0.0.1` uniquement |
| M14 | **Accès au démon Docker** (contrôle total de la machine) | Docker Desktop : le démon tourne dans la VM WSL2, pas sur Windows. Son accès (canal nommé) est réservé au groupe `docker-users`, qui ne contient que l'opérateur. API TCP 2375 désactivée | `Get-LocalGroupMember docker-users` : 1 membre ; aucun port 2375/2376 à l'écoute | un membre de `docker-users` équivaut à un administrateur (il peut monter `C:\`) : groupe à garder minimal |
| M15 | **Secrets divulgués** (dépôt Git, archive du code) | `.env`, `mosquitto/passwd`, certificats et clés, `secrets.h`, `ca_cert.h` dans `.gitignore` ; secrets générés localement ; mots de passe MQTT hachés dans `passwd` | `git ls-files` ne contient aucun de ces fichiers | le mot de passe OTA de l'ESP32 doit être changé dans `secrets.h` (la valeur d'exemple est connue) |
| M16 | **Mise à jour pirate du firmware** (OTA) | OTA protégé par mot de passe (`OTA_PASSWORD` dans `secrets.h`, non versionné) | — | l'OTA d'Arduino n'est pas chiffré : sur un réseau partagé, un mot de passe faible pourrait être cassé. Désactiver l'OTA en démonstration ou utiliser un mot de passe long |
| M17 | **Saturation du disque** (logs, base, clips) | rotation des logs (3 × 10 Mo par conteneur), purge des mesures (7 j) et des clips (3 j, 500 Mo max), supervision en direct | panneau « Supervision machine », `tools/supervision.ps1` | — |

## 3. Chiffrement : ce qui est chiffré, et avec quoi

| Lien | Protocole | Version minimum | Certificat |
|---|---|---|---|
| ESP32 → broker | MQTT sur TLS (8883), TLS mutuel | TLS 1.2 | le broker présente `server.crt` (IP du PC dans le CN et le SAN, RSA 2048, SHA-256) ; l'ESP32 présente `clients/esp32.crt` ; les deux signés par la CA du projet |
| Navigateur → dashboard, API, vidéo | HTTPS (443), TLS mutuel | TLS 1.2 (1.3 négocié) | le serveur présente `server.crt` ; le navigateur présente le certificat de son poste (`posteN`) |
| Backend → Gmail | SMTP STARTTLS (587) | celle de Gmail | autorité publique |
| Mots de passe MQTT au repos | `mosquitto_passwd` | — | haché (PBKDF2-SHA512) |

La CA est créée une seule fois (2 ans) et reste sur le PC (`mosquitto/certs/ca.key`). Le
certificat du serveur est resigné automatiquement quand l'adresse du PC change ; les
certificats des postes ne changent pas.

## 4. Accès réservé aux postes autorisés (certificats clients)

Tout le monde sur le Wi-Fi de l'école peut joindre `https://<IP du PC>`. Pour que seuls les
postes de l'équipe puissent ouvrir le dashboard, le proxy pratique le **TLS mutuel** : le
serveur prouve son identité avec `server.crt`, et chaque navigateur doit prouver la sienne
avec un certificat client.

| Fichier (`mosquitto/certs/clients/`) | Rôle | À faire |
|---|---|---|
| `posteN.crt` | certificat du poste N, signé par la CA, usage « authentification client » uniquement | reste sur le serveur : sa présence = poste autorisé |
| `posteN.key` | clé privée du poste | incluse dans le `.p12`, peut être supprimée du serveur après distribution |
| `posteN.p12` | certificat + clé + CA, protégé par mot de passe : **le fichier à donner à la personne** | à remettre en main propre (clé USB), puis supprimer du serveur |
| `posteN.mot-de-passe.txt` | mot de passe du `.p12` | à donner séparément, puis supprimer |
| `autorises.pem` | liste des certificats acceptés par le proxy (poste1 à posteN) | régénérée par `lancer.ps1` |

**Fonctionnement.**

1. Au premier lancement, `lancer.ps1` crée la CA, le certificat du serveur et `NB_CLIENTS`
   certificats clients (5 par défaut). Aux lancements suivants, il ne crée que ce qui manque.
2. Chaque personne autorisée importe son `posteN.p12` dans Windows (magasin « Personnel »)
   et la CA (magasin « Autorités de certification racines de confiance »). Le navigateur
   propose alors ce certificat en ouvrant `https://<IP du PC>`.
3. À chaque connexion, Caddy vérifie que le certificat présenté est signé par la CA **et**
   fait partie de `autorises.pem`. Sinon, la connexion TLS est refusée : aucune page,
   aucune API, aucun flux vidéo n'est accessible.
4. Ensuite seulement, la connexion `admin` et le jeton JWT s'appliquent (deux facteurs :
   ce que le poste possède, ce que l'utilisateur sait).

**Révoquer un poste** (ordinateur perdu, personne qui quitte l'équipe) : supprimer
`posteN.crt` sur le serveur et relancer `lancer.ps1`. Un nouveau certificat `posteN` est
créé, l'ancien n'est plus dans la liste et il est refusé immédiatement.

**Ce qui n'est pas concerné** : l'accès local du PC serveur (Swagger sur `127.0.0.1:8000`,
dashboard de développement sur `localhost:5173`) ne passe pas par le proxy.

**L'ESP32 aussi (MQTT 8883).** Le broker exige également un certificat client sur le port
8883 (`require_certificate true`). L'ESP32 a le sien, `clients/esp32.crt` (valable 2 ans,
indépendant de l'IP) ; `lancer.ps1` en tire `firmware/sentinel_temp/client_cert.h`
(certificat et clé, non versionné) que le firmware charge avec `setCertificate` et
`setPrivateKey`. Le mot de passe `esp32` et les ACL restent exigés après la poignée de main.
Contrairement à Caddy, Mosquitto ne sait pas restreindre à une liste précise : il accepte
tout certificat client signé par la CA.

## 5. Périmètre

La sécurité du prototype porte sur la stack SENTINEL-X : exposition minimale (deux ports,
tous deux chiffrés), chiffrement TLS de bout en bout, authentification et contrôle d'accès,
conteneurs durcis. Le durcissement du système d'exploitation hôte (pare-feu Windows,
services, comptes) n'entre pas dans le périmètre du projet.

À faire avant la démonstration : choisir un `OTA_PASSWORD` long dans
`firmware/sentinel_temp/secrets.h` (la valeur d'exemple est publique).

## 6. Protocole de preuves (soutenance)

À réaliser sur le rendu final, depuis **un autre poste du Wi-Fi**.

1. **Scan de ports**
   `nmap -Pn -sS -p 1-10000 --open <IP du PC>` : côté SENTINEL-X, seuls 443 et 8883
   répondent (1883, 8000, 8001, 5432, 8080 fermés). `nmap -sV -p 443,8883 --script
   ssl-enum-ciphers <IP>` : TLS 1.2/1.3, suites fortes.
2. **Chiffrement MQTT : Wireshark**
   - capture sur la carte Wi-Fi, filtre `tcp.port == 8883` pendant que l'ESP32 publie :
     seulement des trames « TLSv1.x Application Data », contenu illisible ; en TLS 1.2, la
     poignée de main montre la demande de certificat du broker (« Certificate Request ») et
     le certificat présenté par l'ESP32 ;
   - capture sur la boucle locale (adaptateur « Npcap Loopback »), filtre `mqtt`, en
     publiant une mesure de test sur 1883 avec `tools/simulate_sensors.py` : topic
     `sentinelx/table1/sensors` et JSON en clair. La comparaison des deux captures est la
     preuve attendue par le jury.
3. **HTTPS** : capture `tcp.port == 443` pendant l'utilisation du dashboard (illisible) ;
   certificat affiché dans le navigateur (émis par « Sentinel-X CA G9 »).
4. **Accès réservé aux postes autorisés** : depuis un poste sans certificat client,
   `https://<IP>` affiche `ERR_BAD_SSL_CLIENT_AUTH_CERT` ; depuis un poste autorisé, le
   navigateur propose le certificat « Sentinel-X posteN » puis affiche le dashboard.
5. **Authentification** : `curl` sans jeton → 401 sur `/api/v1/tables/table1/commande` ;
   `mosquitto_sub` anonyme → refus ; flux vidéo sans session → 401.
6. **Conteneurs** : `docker compose exec backend id` (uid 10001),
   `docker inspect --format '{{.HostConfig.CapDrop}} {{.HostConfig.ReadonlyRootfs}}' sentinelx-backend-1`.
