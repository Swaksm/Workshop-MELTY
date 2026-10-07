# Etat de la machine en une commande (MCO) : CPU/RAM par conteneur, taille des logs
# (dont Mosquitto) et des volumes. Complète l'API /api/v1/supervision et cAdvisor.
# Usage : .\tools\supervision.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "=== CPU / RAM par conteneur ==="
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"

Write-Host ""
Write-Host "=== Taille des logs (rotation : 3 fichiers de 10 Mo max par conteneur) ==="
$conteneurs = docker compose ps -q
foreach ($id in $conteneurs) {
    $nom = docker inspect --format "{{.Name}}" $id
    $dossier = (docker inspect --format "{{.LogPath}}" $id) -replace "/[^/]+$", ""
    $taille = docker run --rm -v "/var/lib/docker/containers:/c:ro" alpine:3.20 sh -c "du -ch $($dossier -replace '^/var/lib/docker/containers', '/c')/*-json.log* | tail -1 | cut -f1"
    Write-Host ("{0,-28} {1}" -f $nom.TrimStart("/"), $taille)
}

Write-Host ""
Write-Host "=== Volumes de données ==="
docker system df -v | Select-String -Pattern "VOLUME NAME|sentinelx_"

Write-Host ""
Write-Host "=== Base, clips, broker (API) ==="
try {
    $s = Invoke-RestMethod http://localhost:8000/api/v1/supervision -TimeoutSec 5
    Write-Host "Mesures en base : $($s.base.mesures) ($($s.base.taille_mesures_mo) Mo, base $($s.base.taille_base_mo) Mo)"
    Write-Host "Clips video     : $($s.media.clips) ($($s.media.taille_mo) / $($s.media.max_mo) Mo)"
    Write-Host "Clients MQTT    : $($s.mqtt.clients_connectes), messages recus/min : $($s.mqtt.messages_recus_par_min)"
    Write-Host "Derniere purge  : $($s.retention.dernier_passage.date)"
} catch {
    Write-Host "API injoignable : $_"
}
