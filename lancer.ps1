param(
    [int]$CameraIndex = 0,
    [switch]$SansVision,
    [switch]$SansFront,
    [switch]$Build,             # gardé pour compatibilité : la stack est toujours reconstruite
    [string]$ForcerIp           # force l'IP du serveur si la détection automatique se trompe
)

$ErrorActionPreference = "Stop"
$racine = $PSScriptRoot
$logs = Join-Path $racine "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

function Test-Docker {
    cmd /c "docker info >nul 2>&1"
    return $LASTEXITCODE -eq 0
}

function Attendre-Docker {
    if (Test-Docker) { return }
    Write-Host "Démarrage de Docker Desktop..."
    Start-Process "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"
    for ($i = 0; $i -lt 90; $i++) {
        Start-Sleep -Seconds 2
        if (Test-Docker) { return }
    }
    throw "Docker ne répond pas après 3 minutes. Lance Docker Desktop à la main puis relance ce script."
}

Set-Location $racine

# Adresse de repli quand le Wi-Fi est coupé. Pas 127.0.0.1 : docker-compose.yml
# publie déjà des ports sur 127.0.0.1, les publier deux fois ferait échouer le lancement.
$IP_REPLI = "127.0.0.2"

# Adresse du PC sur le Wi-Fi de l'école : la carte Wi-Fi physique connectée qui a
# une passerelle. Le point d'accès mobile Windows (pas de passerelle) et les cartes
# virtuelles (Docker, WSL) sont ignorés, quel que soit le nom de la carte.
function Get-IpServeur {
    $config = Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object {
        $_.IPv4DefaultGateway -and
        $_.NetAdapter.Status -eq "Up" -and
        $_.NetAdapter.PhysicalMediaType -eq "Native 802.11"
    } | Select-Object -First 1
    if ($config) {
        $ip = $config.IPv4Address | Where-Object { $_.IPAddress -notlike "169.254.*" } | Select-Object -First 1
        if ($ip) { return $ip.IPAddress }
    }
    return $IP_REPLI
}

function Definir-Variable($nom, $valeur) {
    $fichier = "$racine\.env"
    if (-not (Test-Path $fichier)) { Copy-Item "$racine\.env.example" $fichier }
    $lignes = Get-Content $fichier
    if ($lignes -match "^$nom=") {
        $lignes = $lignes -replace "^$nom=.*", "$nom=$valeur"
    } else {
        $lignes += "$nom=$valeur"
    }
    Set-Content -Path $fichier -Value $lignes -Encoding ascii
}

function Lire-Env($nom) {
    $fichier = "$racine\.env"
    if (-not (Test-Path $fichier)) { return $null }
    $ligne = Get-Content $fichier | Where-Object { $_ -match "^$nom=" } | Select-Object -First 1
    if ($ligne) { return $ligne.Substring($nom.Length + 1) }
    return $null
}

$ipPrecedente = Lire-Env "SERVER_IP"
$ipServeur = if ($ForcerIp) { $ForcerIp } else { Get-IpServeur }
Definir-Variable "SERVER_IP" $ipServeur
if ($ipServeur -eq $IP_REPLI) {
    Write-Host "Wi-Fi inactif : l'ESP32 ne pourra pas se connecter. Vérifie la connexion au Wi-Fi puis relance."
} else {
    Write-Host "PC détecté sur le Wi-Fi : $ipServeur"
    if ($ipPrecedente -and $ipPrecedente -ne $IP_REPLI -and $ipPrecedente -ne $ipServeur) {
        Write-Host "ATTENTION : l'IP du PC a changé ($ipPrecedente -> $ipServeur). Il faudra reflasher l'ESP32 (MQTT_HOST)."
    }
}

# Secret aléatoire tiré par le générateur cryptographique de Windows
# (Get-Random n'est pas fait pour des mots de passe)
function New-Secret([int]$longueur = 24) {
    $alphabet = [char[]]((48..57) + (65..90) + (97..122))
    $octets = New-Object byte[] $longueur
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($octets)
    -join ($octets | ForEach-Object { $alphabet[$_ % $alphabet.Length] })
}

foreach ($nom in @("MQTT_PASSWORD", "VISION_MQTT_PASSWORD", "ESP32_MQTT_PASSWORD", "ADMIN_PASSWORD")) {
    $valeur = Lire-Env $nom
    if (-not $valeur -or $valeur -eq "change-me") {
        Definir-Variable $nom (New-Secret)
    }
}
Definir-Variable "MQTT_USER" "backend"
if (-not (Lire-Env "ADMIN_USER")) { Definir-Variable "ADMIN_USER" "admin" }
if (-not (Lire-Env "JWT_SECRET") -or (Lire-Env "JWT_SECRET") -eq "change-me") {
    Definir-Variable "JWT_SECRET" (New-Secret 48)   # clé de signature des jetons de l'API
}

function Ecrire-Passwd {
    $pwBackend = Lire-Env "MQTT_PASSWORD"
    $pwVision = Lire-Env "VISION_MQTT_PASSWORD"
    $pwEsp = Lire-Env "ESP32_MQTT_PASSWORD"
    $dossier = (Join-Path $racine "mosquitto") -replace '\\', '/'
    & docker run --rm -v "${dossier}:/work" eclipse-mosquitto:2 sh -c "rm -f /work/passwd && mosquitto_passwd -b -c /work/passwd backend $pwBackend && mosquitto_passwd -b /work/passwd vision $pwVision && mosquitto_passwd -b /work/passwd esp32 $pwEsp && chmod 644 /work/passwd"
    if ($LASTEXITCODE -ne 0) { throw "Création du fichier mosquitto/passwd échouée." }
}

# Certificat TLS du broker : (re)généré s'il manque ou s'il ne contient pas l'IP actuelle.
# La CA est conservée, donc l'ESP32 n'a pas besoin d'un nouveau certificat.
# Certificats : CA, certificat du serveur et certificats clients des postes autorisés.
# gen-certs.sh ne crée que ce qui manque ; on ne le lance que si quelque chose manque
# ou si le certificat du serveur ne correspond plus à l'IP.
function Ecrire-Certificats($ip) {
    $certs = Join-Path $racine "mosquitto\certs"
    $nbClients = Lire-Env "NB_CLIENTS"
    if (-not $nbClients) { $nbClients = 5 }
    $aFaire = $true
    $serveur = Join-Path $certs "server.crt"
    if (Test-Path $serveur) {
        $cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2 $serveur
        $aFaire = -not ($cert.Subject -eq "CN=$ip" -and $cert.NotAfter -gt (Get-Date).AddDays(7))
    }
    # posteN.crt suffit : .p12, .key et mot de passe peuvent être supprimés après distribution
    $attendus = @("clients\autorises.pem", "clients\esp32.crt", "clients\esp32.key") + (1..$nbClients | ForEach-Object { "clients\poste$_.crt" })
    if ($attendus | Where-Object { -not (Test-Path (Join-Path $certs $_)) }) { $aFaire = $true }
    if (-not $aFaire) { return $false }

    Write-Host "Certificats TLS (serveur $ip, $nbClients postes autorisés)..."
    $dossier = (Join-Path $racine "mosquitto") -replace '\\', '/'
    # CERTS_DIR : le script est copié dans /tmp (fins de ligne), il doit écrire dans le dossier monté
    & docker run --rm -v "${dossier}:/work" -e CERTS_DIR=/work/certs -e NB_CLIENTS=$nbClients alpine:3.20 sh -c "apk add --no-cache openssl >/dev/null && sed 's/\r$//' /work/gen-certs.sh > /tmp/gen.sh && sh /tmp/gen.sh $ip" | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "Création des certificats TLS échouée." }
    Write-Host "Certificats des postes autorisés : mosquitto\certs\clients\posteN.p12 (mot de passe dans posteN.mot-de-passe.txt)."
    return $true
}

# Fichiers locaux du firmware (non versionnés) : CA à jour et IP du broker à jour.
function Mettre-A-Jour-Firmware($ip) {
    $dossier = Join-Path $racine "firmware\sentinel_temp"
    $ca = (Get-Content (Join-Path $racine "mosquitto\certs\ca.crt") -Raw).Trim()
    $contenu = "// Genere par lancer.ps1 a partir de mosquitto/certs/ca.crt, ne pas versionner.`nconst char* CA_CERT = R`"EOF(`n$ca`n)EOF`";`n"
    $fichierCa = Join-Path $dossier "ca_cert.h"
    $ancien = if (Test-Path $fichierCa) { [System.IO.File]::ReadAllText($fichierCa) } else { "" }
    if ($ancien -ne $contenu) {
        [System.IO.File]::WriteAllText($fichierCa, $contenu)
        Write-Host "firmware\sentinel_temp\ca_cert.h mis à jour : reflasher l'ESP32."
    }

    # certificat et clé de l'ESP32 pour le TLS mutuel avec le broker
    $clients = Join-Path $racine "mosquitto\certs\clients"
    $certEsp = (Get-Content (Join-Path $clients "esp32.crt") -Raw).Trim()
    $cleEsp = (Get-Content (Join-Path $clients "esp32.key") -Raw).Trim()
    $contenu = "// Genere par lancer.ps1 a partir de mosquitto/certs/clients/esp32.crt et esp32.key.`n" +
        "// Contient la cle privee de l'ESP32 : ne pas versionner, ne pas diffuser.`n" +
        "const char* CLIENT_CERT = R`"EOF(`n$certEsp`n)EOF`";`n`n" +
        "const char* CLIENT_KEY = R`"EOF(`n$cleEsp`n)EOF`";`n"
    $fichierClient = Join-Path $dossier "client_cert.h"
    $ancien = if (Test-Path $fichierClient) { [System.IO.File]::ReadAllText($fichierClient) } else { "" }
    if ($ancien -ne $contenu) {
        [System.IO.File]::WriteAllText($fichierClient, $contenu)
        Write-Host "firmware\sentinel_temp\client_cert.h mis à jour : reflasher l'ESP32."
    }

    $secrets = Join-Path $dossier "secrets.h"
    if ($ip -ne $IP_REPLI -and (Test-Path $secrets)) {
        $texte = [System.IO.File]::ReadAllText($secrets)
        $nouveau = $texte -replace '#define MQTT_HOST "[^"]*"', "#define MQTT_HOST `"$ip`""
        if ($nouveau -ne $texte) {
            [System.IO.File]::WriteAllText($secrets, $nouveau)
            Write-Host "firmware\sentinel_temp\secrets.h : MQTT_HOST = $ip. Reflasher l'ESP32 (OTA possible)."
        }
    }
}

Attendre-Docker
Ecrire-Passwd
$certsRegeneres = Ecrire-Certificats $ipServeur
Mettre-A-Jour-Firmware $ipServeur
Write-Host "1/3 Stack Docker (base, broker MQTT, backend, proxy HTTPS)..."
# Toujours --build : après un git pull, une image restée à l'ancienne version ferait
# tourner un vieux backend avec le nouveau dashboard. Sans changement, le cache de
# Docker rend la reconstruction quasi instantanée.
cmd /c "docker compose up -d --build"
if ($LASTEXITCODE -ne 0) { throw "docker compose up a échoué." }
if ($certsRegeneres) {
    # Mosquitto et Caddy ne lisent leur certificat qu'au démarrage
    cmd /c "docker compose restart mosquitto proxy"
}

if (-not $SansFront) {
    Write-Host "2/3 Dashboard (Vite)..."
    if (-not (Test-Path "$racine\frontend\node_modules")) {
        # depuis le dossier frontend : "npm --prefix ... install" cherche package.json à la racine
        cmd /c "cd /d `"$racine\frontend`" && npm install"
        if ($LASTEXITCODE -ne 0) { throw "npm install a échoué." }
    }
    Start-Process -FilePath "cmd.exe" `
        -ArgumentList "/c npm --prefix `"$racine\frontend`" run dev -- --host localhost --port 5173" `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$logs\front.log" -RedirectStandardError "$logs\front.err"
}

if (-not $SansVision) {
    Write-Host "3/3 Module vision (webcam $CameraIndex)..."
    $py = "$racine\vision\.venv\Scripts\python.exe"
    if (-not (Test-Path $py)) {
        py -3.10 -m venv "$racine\vision\.venv"
        & $py -m pip install -q --upgrade pip
        & $py -m pip install -q torch==2.5.1 torchvision==0.20.1 --index-url https://download.pytorch.org/whl/cpu
        & $py -m pip install -q -r "$racine\vision\requirements.txt"
        if ($LASTEXITCODE -ne 0) { throw "Installation des dépendances vision échouée." }
    }
    $env:CAMERA_INDEX = "$CameraIndex"
    $env:VISION_MQTT_USER = "vision"
    $env:VISION_MQTT_PASSWORD = Lire-Env "VISION_MQTT_PASSWORD"
    Start-Process -FilePath $py -ArgumentList "app.py" -WorkingDirectory "$racine\vision" `
        -WindowStyle Hidden `
        -RedirectStandardOutput "$logs\vision.log" -RedirectStandardError "$logs\vision.err"
}

Write-Host ""
Write-Host "Prêt :"
Write-Host "  Dashboard HTTPS : https://localhost  (autres postes : https://$ipServeur)"
Write-Host "  Dashboard dev   : http://localhost:5173"
Write-Host "  Swagger         : http://localhost:8000/docs (PC uniquement)"
Write-Host "  Supervision     : http://localhost:8080 (cAdvisor, PC uniquement)"
Write-Host "  Connexion       : $(Lire-Env 'ADMIN_USER') / mot de passe ADMIN_PASSWORD du fichier .env"
Write-Host "  Accès HTTPS     : réservé aux postes autorisés. Sur chaque poste, une fois, importer"
Write-Host "                    son certificat (posteN.p12, mot de passe dans posteN.mot-de-passe.txt)"
Write-Host "                    et la CA du serveur :"
Write-Host "                    Import-PfxCertificate -FilePath .\posteN.p12 -CertStoreLocation Cert:\CurrentUser\My -Password (Read-Host -AsSecureString)"
Write-Host "                    Import-Certificate -FilePath .\ca.crt -CertStoreLocation Cert:\CurrentUser\Root"
Write-Host "Journaux dans le dossier logs\. Pour tout arrêter : .\arreter.ps1"
