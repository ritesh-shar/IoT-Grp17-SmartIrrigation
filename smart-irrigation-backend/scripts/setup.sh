#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env. Edit its passwords, then run this script again."
  exit 1
fi

set -a
# shellcheck disable=SC1091
source ./.env
set +a

: "${MQTT_PASSWORD:?Set MQTT_PASSWORD in .env}"
: "${DEVICE_ID:?Set DEVICE_ID in .env}"
: "${DEVICE_MQTT_PASSWORD:?Set DEVICE_MQTT_PASSWORD in .env}"

mkdir -p mosquitto/config mosquitto/data mosquitto/log

docker run --rm -v "$PWD/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 \
  mosquitto_passwd -b -c /mosquitto/config/passwordfile backend "$MQTT_PASSWORD"
docker run --rm -v "$PWD/mosquitto/config:/mosquitto/config" eclipse-mosquitto:2 \
  mosquitto_passwd -b /mosquitto/config/passwordfile "$DEVICE_ID" "$DEVICE_MQTT_PASSWORD"

docker compose up -d
echo "Infrastructure started. Run: npm install && npm run dev"
