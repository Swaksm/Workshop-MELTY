#!/bin/sh
# Génère les certificats TLS dans mosquitto/certs/, uniquement ceux qui manquent.
# Usage : sh mosquitto/gen-certs.sh IP_DU_SERVEUR
#   CERTS_DIR=/chemin  dossier des certificats (défaut : mosquitto/certs à côté du script)
#   NB_CLIENTS=5       nombre de postes autorisés à ouvrir le dashboard (défaut : 5)
#
# - CA (ca.crt / ca.key) : créée une seule fois. L'ESP32 et les navigateurs la
#   connaissent : tant qu'on la garde, rien à redistribuer.
# - Certificat du serveur (server.crt) : IP dans le CN et le SAN. Refait s'il manque,
#   si l'IP a changé ou s'il expire dans moins de 7 jours.
# - Certificats clients (clients/posteN) : un par poste autorisé à ouvrir le dashboard
#   en HTTPS. Créés si posteN.crt manque, jamais écrasés. Le proxy n'accepte que les
#   certificats listés dans clients/autorises.pem. Après distribution, posteN.p12,
#   posteN.key et le mot de passe peuvent être supprimés du serveur ; supprimer
#   posteN.crt révoque le poste (un nouveau certificat est créé au lancement suivant).
# - Certificat de l'ESP32 (clients/esp32) : présenté au broker MQTT (TLS mutuel sur
#   8883). Créé s'il manque, indépendant de l'IP. Sa clé reste sur le serveur :
#   lancer.ps1 en tire firmware/sentinel_temp/client_cert.h.
set -eu
IP="${1:?Usage : gen-certs.sh IP_DU_SERVEUR}"
NB_CLIENTS="${NB_CLIENTS:-5}"
DIR="${CERTS_DIR:-$(cd "$(dirname "$0")" && pwd)/certs}"
mkdir -p "$DIR/clients"
cd "$DIR"

# 1. Autorité de certification du projet (une seule fois, valable 2 ans)
if [ ! -f ca.key ] || [ ! -f ca.crt ]; then
  openssl req -x509 -new -nodes -newkey rsa:2048 -sha256 -days 730 \
    -keyout ca.key -out ca.crt -subj "/CN=Sentinel-X CA G9"
  echo "Nouvelle CA créée : ca.crt doit être recopié dans le firmware de l'ESP32."
fi

# 2. Certificat du serveur, valable pour l'IP du PC et le local
if [ ! -f server.crt ] || [ ! -f server.key ] \
   || [ "$(openssl x509 -in server.crt -noout -subject -nameopt RFC2253)" != "subject=CN=$IP" ] \
   || ! openssl x509 -in server.crt -noout -checkend 604800 >/dev/null; then
  openssl req -new -nodes -newkey rsa:2048 -sha256 \
    -keyout server.key -out server.csr -subj "/CN=$IP"
  printf "subjectAltName=IP:%s,IP:127.0.0.1,DNS:localhost,DNS:mosquitto\nextendedKeyUsage=serverAuth\n" "$IP" > server.ext
  openssl x509 -req -sha256 -days 365 -in server.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out server.crt -extfile server.ext
  rm -f server.csr server.ext
  echo "Certificat du serveur créé pour $IP."
fi

# 3. Certificats clients : un par poste autorisé (usage « authentification client »
#    uniquement, ils ne peuvent pas servir à se faire passer pour le serveur)
i=1
while [ "$i" -le "$NB_CLIENTS" ]; do
  n="poste$i"
  if [ ! -f "clients/$n.crt" ]; then
    openssl req -new -nodes -newkey rsa:2048 -sha256 \
      -keyout "clients/$n.key" -out "clients/$n.csr" -subj "/CN=Sentinel-X $n"
    printf "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n" > "clients/$n.ext"
    openssl x509 -req -sha256 -days 365 -in "clients/$n.csr" -CA ca.crt -CAkey ca.key \
      -CAcreateserial -out "clients/$n.crt" -extfile "clients/$n.ext"
    # fichier à importer sur le poste (certificat + clé + CA), protégé par un mot de passe
    mdp="$(openssl rand -hex 8)"
    openssl pkcs12 -export -in "clients/$n.crt" -inkey "clients/$n.key" -certfile ca.crt \
      -name "Sentinel-X $n" -out "clients/$n.p12" -passout "pass:$mdp"
    echo "$mdp" > "clients/$n.mot-de-passe.txt"
    rm -f "clients/$n.csr" "clients/$n.ext"
    echo "Certificat client créé : clients/$n.p12"
  fi
  i=$((i + 1))
done

# 4. Certificat client de l'ESP32 (TLS mutuel avec le broker MQTT)
if [ ! -f clients/esp32.crt ] || [ ! -f clients/esp32.key ]; then
  openssl req -new -nodes -newkey rsa:2048 -sha256 \
    -keyout clients/esp32.key -out clients/esp32.csr -subj "/CN=esp32"
  printf "extendedKeyUsage=clientAuth\nkeyUsage=digitalSignature\n" > clients/esp32.ext
  openssl x509 -req -sha256 -days 730 -in clients/esp32.csr -CA ca.crt -CAkey ca.key \
    -CAcreateserial -out clients/esp32.crt -extfile clients/esp32.ext
  rm -f clients/esp32.csr clients/esp32.ext
  echo "Certificat client de l'ESP32 créé : reflasher l'ESP32 (client_cert.h)."
fi

# Liste des postes acceptés par le proxy HTTPS (seulement poste1 à posteN, pas l'ESP32)
: > clients/autorises.pem
i=1
while [ "$i" -le "$NB_CLIENTS" ]; do
  cat "clients/poste$i.crt" >> clients/autorises.pem
  i=$((i + 1))
done

chmod 644 ca.crt server.crt server.key clients/autorises.pem   # lisibles par mosquitto et caddy
chmod 600 ca.key
for f in clients/*.key clients/*.p12 clients/*.mot-de-passe.txt; do
  if [ -f "$f" ]; then chmod 600 "$f"; fi
done
rm -f ca.srl
openssl x509 -in server.crt -noout -subject -ext subjectAltName
