# Smart Irrigation Backend

Starter backend for ESP32 soil sensors. It provides:

- Mosquitto MQTT broker with password authentication and per-device ACLs
- PostgreSQL persistence for device status, sensor readings, and command acknowledgements
- Node.js/Express REST API
- Socket.IO live updates for a React frontend
- Remote ESP32 threshold configuration and reading requests

## Requirements

- Docker Desktop (running)
- Node.js 20 or newer
- ESP32 and laptop on the same network (or otherwise routable)
- Arduino libraries: PubSubClient and ArduinoJson

## 1. Configure credentials

Copy `.env.example` to `.env`:

```powershell
Copy-Item .env.example .env
```

Edit `.env`. Set strong, unique values for:
- `MQTT_PASSWORD` (backend MQTT account)
- `DEVICE_MQTT_PASSWORD` (ESP32 MQTT account)
- `DB_PASSWORD` (PostgreSQL; keep the password in `DATABASE_URL` in sync)

Keep `DEVICE_ID=esp32_soil_001` for the supplied firmware, or change it in both `.env` and the Arduino sketch. The MQTT username for a device is its device ID.

## 2. Start infrastructure (Windows PowerShell)

From this folder:

```powershell
.\scripts\setup.ps1
```

The script creates the Mosquitto password file and starts Mosquitto + PostgreSQL.

If PowerShell blocks scripts, run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1
```

Linux/macOS:

```bash
cp .env.example .env
# Edit .env and set strong passwords
chmod +x scripts/setup.sh
./scripts/setup.sh
```

Ports:
- MQTT TCP: `1883`
- PostgreSQL: `5432`

## 3. Start the Node backend

```bash
npm install
npm run dev
```

Backend listens on `http://localhost:3000`.

Check:

```text
GET http://localhost:3000/api/health
```

Expected JSON when both services are up:

```json
{
  "status": "ok",
  "mqtt_connected": true,
  "database_connected": true
}
```

## 4. Configure the ESP32

In `smart_irrigate_mqtt.ino` set:
- `WIFI_SSID` and `WIFI_PASSWORD`
- `MQTT_SERVER` to the laptop's current LAN IPv4 address (the supplied setup uses `10.1.0.56`; update it if DHCP changes it)
- `DEVICE_ID` to the same value as `.env` (`esp32_soil_001`)
- `MQTT_PASSWORD` to the exact value of `DEVICE_MQTT_PASSWORD` in `.env`

Install Arduino libraries:
- PubSubClient by Nick O'Leary
- ArduinoJson by Benoit Blanchon (version 7)

Select your ESP32 board and port, upload, then open Serial Monitor at 115200 baud.

**Wi-Fi note:** many classic ESP32 boards support 2.4 GHz only. The laptop may use 5 GHz, but the router must allow 2.4 GHz clients to reach the laptop (no guest/client isolation).

## 5. REST API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/health` | API, MQTT and database health |
| GET | `/api/devices` | All known devices |
| GET | `/api/devices/:id` | Device status and latest reading |
| GET | `/api/devices/:id/latest` | Latest reading |
| GET | `/api/devices/:id/history?limit=100` | Recent readings (max 1000) |
| POST | `/api/devices/:id/command` | Send a command |
| GET | `/api/commands/:commandId` | Look up command acknowledgement |

Example command:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:3000/api/devices/esp32_soil_001/command" `
  -ContentType "application/json" `
  -Body '{"command":"set_threshold","value":2300}'
```

Request an immediate reading:

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://localhost:3000/api/devices/esp32_soil_001/command" `
  -ContentType "application/json" `
  -Body '{"command":"request_reading"}'
```

A successful HTTP response means the command was accepted by MQTT, not necessarily executed. The ESP32 sends an acknowledgement to its `/ack` topic. The API returns a `command_id`; query `/api/commands/:commandId` or listen for Socket.IO `command_ack`.

## 6. MQTT topics

For device `esp32_soil_001`:

- Publish telemetry: `smart-irrigation/devices/esp32_soil_001/telemetry`
- Publish retained availability: `smart-irrigation/devices/esp32_soil_001/availability`
- Publish state: `smart-irrigation/devices/esp32_soil_001/state`
- Subscribe commands: `smart-irrigation/devices/esp32_soil_001/command`
- Publish command acknowledgements: `smart-irrigation/devices/esp32_soil_001/ack`

Other applications can subscribe to telemetry using their own authenticated MQTT account. Do not share the backend or device credentials with frontend/browser code.

## 7. React frontend connection

Install:

```bash
npm install socket.io-client
```

Connect from React:

```js
import { io } from "socket.io-client";

const socket = io("http://localhost:3000");
socket.on("initial_devices", console.log);
socket.on("sensor_update", console.log);
socket.on("device_availability", console.log);
socket.on("device_state", console.log);
socket.on("command_ack", console.log);
```

Use REST endpoints for device/history queries and Socket.IO for live updates.

## Calibration and safety

- `DRY_VALUE` and `WET_VALUE` in the firmware are placeholders. Measure the raw ADC value in dry and wet soil and calibrate them.
- The original threshold `2500` is retained. Confirm the sensor's raw readings before relying on dry/wet automation.
- This starter only implements a soil sensor and threshold configuration. Do not connect a pump directly to an ESP32 GPIO; use a properly rated relay/MOSFET driver, flyback protection where applicable, and a safe default-off design.
- MQTT port 1883 is unencrypted. Keep it on a trusted LAN for this prototype. Before remote/cloud access, configure TLS, firewall restrictions, strong credentials, and per-device ACLs. Do not port-forward 1883 to the public internet.
- The API is a development starter and currently has no user login/API authentication. Do not expose it publicly until authentication, authorization, rate limits, and HTTPS are added.
- For production, add device provisioning, credential rotation, command expiry/idempotency, audit logs, backups, and monitoring.

## Stop services

```bash
docker compose down
```

Data persists in the Docker PostgreSQL volume and `mosquitto/data`. To remove the database volume too (destructive):

```bash
docker compose down -v
```
