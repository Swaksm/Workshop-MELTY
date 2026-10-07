# 1. Compilation du dashboard React
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 2. Reverse proxy HTTPS (Caddy) qui sert le dashboard compilé
FROM caddy:2.8-alpine
COPY --from=build /app/dist /srv
# L'image officielle donne au binaire le droit d'écouter sous le port 1024. Inutile
# ici (Caddy écoute sur 8443) et incompatible avec no-new-privileges : on le retire.
RUN apk add --no-cache libcap && setcap -r /usr/bin/caddy && apk del libcap
# Caddy n'a besoin d'écrire que dans /tmp (monté en tmpfs, conteneur en lecture seule)
ENV XDG_DATA_HOME=/tmp/caddy-data \
    XDG_CONFIG_HOME=/tmp/caddy-config
USER 65534:65534
EXPOSE 8443
