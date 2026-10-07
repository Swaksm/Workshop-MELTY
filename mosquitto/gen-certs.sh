#!/bin/sh
# Génère les certificats TLS du broker dans mosquitto/certs/
# Usage : sh mosquitto/gen-certs.sh IP_DU_SERVEUR
#         (CERTS_DIR=/chemin pour choisir le dossier, défaut : mosquitto/certs à côté du script)
#
# - La CA (ca.crt / ca.key) n'est créée qu'une seule fois : c'est elle que
#   l'ESP32 connaît (firmware/sentinel_temp/ca_cert.h). Tant qu'on la garde,
#   pas besoin de reflasher le certificat dans l'ESP32.
# - Le certificat du broker (server.crt) est resigné à chaque appel avec l'IP
#   donnée, dans le CN et le SAN : l'ESP32 vérifie que l'IP qu'il contacte est
#   bien celle écrite dans le certificat.
set -eu
IP="${1:?Usage : gen-certs.sh IP_DU_SERVEUR}"
DIR="${CERTS_DIR:-$(cd "$(dirname "$0")" && pwd)/certs}"
mkdir -p "$DIR"
cd "$DIR"

# 1. Autorité de certification du projet (une seule fois, valable 2 ans)
if [ ! -f ca.key ] || [ ! -f ca.crt ]; then
  openssl req -x509 -new -nodes -newkey rsa:2048 -sha256 -days 730 \
    -keyout ca.key -out ca.crt -subj "/CN=Sentinel-X CA G9"
  echo "Nouvelle CA créée : ca.crt doit être recopié dans le firmware de l'ESP32."
fi

# 2. Clé et demande de certificat du broker
openssl req -new -nodes -newkey rsa:2048 -sha256 \
  -keyout server.key -out server.csr -subj "/CN=$IP"

# 3. Certificat du broker signé par la CA, valable pour l'IP du serveur et le local
printf "subjectAltName=IP:%s,IP:127.0.0.1,DNS:localhost,DNS:mosquitto\nextendedKeyUsage=serverAuth\n" "$IP" > server.ext
openssl x509 -req -sha256 -days 365 -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -extfile server.ext

chmod 644 ca.crt server.crt server.key   # lisibles par l'utilisateur mosquitto (uid 1883)
chmod 600 ca.key                         # la clé de la CA reste privée
rm -f server.csr server.ext ca.srl
openssl x509 -in server.crt -noout -subject -ext subjectAltName
