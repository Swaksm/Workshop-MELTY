#!/bin/sh
# Génère la CA et le certificat TLS du broker dans mosquitto/certs/
# Usage : sh mosquitto/gen-certs.sh [IP_RESEAU_DE_TABLE]   (défaut : 192.168.52.1)
set -eu
IP="${1:-192.168.52.1}"
DIR="$(cd "$(dirname "$0")" && pwd)/certs"
mkdir -p "$DIR"
cd "$DIR"

# 1. Autorité de certification du projet
openssl req -x509 -new -nodes -newkey rsa:2048 -sha256 -days 365 \
  -keyout ca.key -out ca.crt -subj "/CN=Sentinel-X CA G9"

# 2. Clé et demande de certificat du broker
openssl req -new -nodes -newkey rsa:2048 -sha256 \
  -keyout server.key -out server.csr -subj "/CN=sentinel-x-broker"

# 3. Certificat du broker signé par la CA, valable pour le réseau de table et le local
printf "subjectAltName=IP:%s,IP:127.0.0.1,DNS:localhost,DNS:mosquitto\nextendedKeyUsage=serverAuth\n" "$IP" > server.ext
openssl x509 -req -sha256 -days 365 -in server.csr -CA ca.crt -CAkey ca.key \
  -CAcreateserial -out server.crt -extfile server.ext

chmod 644 ca.crt server.crt server.key   # lisibles par l'utilisateur mosquitto (uid 1883)
chmod 600 ca.key                         # la clé de la CA reste privée
rm -f server.csr server.ext ca.srl
openssl x509 -in server.crt -noout -subject -ext subjectAltName