param(
    [int]$CameraIndex = 0,
    [switch]$SansVision,
    [switch]$SansFront
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

$IP_TABLE = "192.168.52.1"

function Get-AdresseHotspot {
    $adresse = Get-NetIPAddress -AddressFamily IPv4 -IPAddress $IP_TABLE -ErrorAction SilentlyContinue
    if ($adresse) { return $IP_TABLE }
    return "127.0.0.2"
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

$hotspot = Get-AdresseHotspot
Definir-Variable "HOTSPOT_IP" $hotspot
if ($hotspot -eq "127.0.0.2") {
    Write-Host "Réseau de table inactif : l'adresse $IP_TABLE est absente (clé Wi-Fi débranchée ou partage arrêté). L'ESP32 ne pourra pas se connecter."
} else {
    Write-Host "Réseau de table détecté : $hotspot"
}

function Lire-Env($nom) {
    $fichier = "$racine\.env"
    if (-not (Test-Path $fichier)) { return $null }
    $ligne = Get-Content $fichier | Where-Object { $_ -match "^$nom=" } | Select-Object -First 1
    if ($ligne) { return $ligne.Substring($nom.Length + 1) }
    return $null
}

function New-Secret {
    -join ((48..57 + 65..90 + 97..122) | Get-Random -Count 24 | ForEach-Object { [char]$_ })
}

foreach ($nom in @("MQTT_PASSWORD", "VISION_MQTT_PASSWORD", "ESP32_MQTT_PASSWORD")) {
    $valeur = Lire-Env $nom
    if (-not $valeur -or $valeur -eq "change-me") {
        Definir-Variable $nom (New-Secret)
    }
}
Definir-Variable "MQTT_USER" "backend"

function Ecrire-Passwd {
    $pwBackend = Lire-Env "MQTT_PASSWORD"
    $pwVision = Lire-Env "VISION_MQTT_PASSWORD"
    $pwEsp = Lire-Env "ESP32_MQTT_PASSWORD"
    $dossier = (Join-Path $racine "mosquitto") -replace '\\', '/'
    & docker run --rm -v "${dossier}:/work" eclipse-mosquitto:2 sh -c "mosquitto_passwd -b -c /work/passwd backend $pwBackend && mosquitto_passwd -b /work/passwd vision $pwVision && mosquitto_passwd -b /work/passwd esp32 $pwEsp && chmod 644 /work/passwd"
    if ($LASTEXITCODE -ne 0) { throw "Création du fichier mosquitto/passwd échouée." }
}

Attendre-Docker
Ecrire-Passwd
Write-Host "1/3 Stack Docker (base, broker MQTT, backend)..."
cmd /c "docker compose up -d --build"
if ($LASTEXITCODE -ne 0) { throw "docker compose up a échoué." }

if (-not $SansFront) {
    Write-Host "2/3 Dashboard (Vite)..."
    if (-not (Test-Path "$racine\frontend\node_modules")) {
        cmd /c "npm --prefix `"$racine\frontend`" install"
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
Write-Host "  Dashboard  : http://localhost:5173"
Write-Host "  API        : http://localhost:8000/docs"
Write-Host "  Vision     : http://localhost:8001/stream"
Write-Host "Journaux dans le dossier logs\. Pour tout arrêter : .\arreter.ps1"
