$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (!(Test-Path ".env")) {
  Copy-Item ".env.example" ".env"
  Write-Host "Created .env from .env.example. Edit its passwords, then run this script again."
  exit 1
}

$values = @{}
Get-Content ".env" | ForEach-Object {
  $line = $_.Trim()
  if ($line -and !$line.StartsWith("#") -and $line.Contains("=")) {
    $parts = $line.Split("=", 2)
    $values[$parts[0].Trim()] = $parts[1].Trim()
  }
}

$backendPassword = $values["MQTT_PASSWORD"]
$deviceId = $values["DEVICE_ID"]
$devicePassword = $values["DEVICE_MQTT_PASSWORD"]

if (!$backendPassword -or !$deviceId -or !$devicePassword) {
  throw "MQTT_PASSWORD, DEVICE_ID and DEVICE_MQTT_PASSWORD must be set in .env"
}

New-Item -ItemType Directory -Force "mosquitto/config", "mosquitto/data", "mosquitto/log" | Out-Null

Write-Host "Creating Mosquitto password file..."
docker run --rm -v "${PWD}/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 `
  mosquitto_passwd -b -c /mosquitto/config/passwordfile backend "$backendPassword"
if ($LASTEXITCODE -ne 0) { throw "Failed creating backend MQTT user" }

docker run --rm -v "${PWD}/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 `
  mosquitto_passwd -b /mosquitto/config/passwordfile "$deviceId" "$devicePassword"
if ($LASTEXITCODE -ne 0) { throw "Failed creating device MQTT user" }

Write-Host "Starting MQTT broker and PostgreSQL..."
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose failed" }

Write-Host ""
Write-Host "Infrastructure started."
Write-Host "MQTT broker: mqtt://127.0.0.1:1883"
Write-Host "PostgreSQL: 127.0.0.1:5432"
Write-Host "Next: npm install ; npm run dev"
