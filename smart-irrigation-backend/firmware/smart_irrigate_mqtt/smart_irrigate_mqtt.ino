#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>

// Match DEVICE_ID and DEVICE_MQTT_PASSWORD in the backend .env file.
#define DEVICE_ID "esp32_soil_001"

// Existing hardware from your uploaded sketch
#define SENSOR_PIN 34
#define RED_LED 26
#define GREEN_LED 25

// Original threshold retained from your sketch
int moistureThreshold = 2500;

// PLACEHOLDERS: calibrate these using your sensor's actual raw readings.
#define DRY_VALUE 3200
#define WET_VALUE 1200

const char* WIFI_SSID = "Ritesh S24";
const char* WIFI_PASSWORD = "ritesh124629";

// Laptop IPv4 from your screenshot. Update if DHCP changes the address.
const char* MQTT_SERVER = "10.18.200.101";
const uint16_t MQTT_PORT = 1883;
const char* MQTT_USERNAME = DEVICE_ID;
const char* MQTT_PASSWORD = "iotgrp17";

const unsigned long PUBLISH_INTERVAL_MS = 2000;
const unsigned long WIFI_RETRY_INTERVAL_MS = 5000;
const unsigned long MQTT_RETRY_INTERVAL_MS = 3000;

WiFiClient wifiClient;
PubSubClient mqttClient(wifiClient);

String baseTopic;
String telemetryTopic;
String availabilityTopic;
String commandTopic;
String stateTopic;
String ackTopic;

unsigned long lastPublishMs = 0;
unsigned long lastWiFiAttemptMs = 0;
bool wifiStarted = false;
unsigned long lastMqttAttemptMs = 0;

int moistureRaw = 0;
float moisturePercent = 0.0f;
bool soilDry = false;

void buildTopics() {
  baseTopic = String("smart-irrigation/devices/") + DEVICE_ID;
  telemetryTopic = baseTopic + "/telemetry";
  availabilityTopic = baseTopic + "/availability";
  commandTopic = baseTopic + "/command";
  stateTopic = baseTopic + "/state";
  ackTopic = baseTopic + "/ack";
}

void readSensor() {
  // Average several ADC samples to reduce noise.
  uint32_t total = 0;
  const int samples = 10;

  for (int i = 0; i < samples; i++) {
    total += analogRead(SENSOR_PIN);
    delay(5);
  }

  moistureRaw = total / samples;
  soilDry = moistureRaw > moistureThreshold;

  // Higher raw reading = drier soil for the sensor convention in your sketch.
  float denominator = (float)(DRY_VALUE - WET_VALUE);
  if (denominator != 0.0f) {
    moisturePercent =
      ((float)(DRY_VALUE - moistureRaw) / denominator) * 100.0f;
  } else {
    moisturePercent = 0.0f;
  }

  moisturePercent = constrain(moisturePercent, 0.0f, 100.0f);

  digitalWrite(RED_LED, soilDry ? HIGH : LOW);
  digitalWrite(GREEN_LED, soilDry ? LOW : HIGH);

  Serial.printf("Raw: %d | Moisture: %.1f%% | Status: %s\n",
                moistureRaw, moisturePercent, soilDry ? "DRY" : "WET");
}

void publishState() {
  if (!mqttClient.connected()) return;

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["threshold"] = moistureThreshold;
  doc["connected"] = true;

  char payload[160];
  size_t length = serializeJson(doc, payload, sizeof(payload));
  mqttClient.publish(stateTopic.c_str(), (const uint8_t*)payload, length, true);
}

void publishTelemetry() {
  if (!mqttClient.connected()) return;

  JsonDocument doc;
  doc["device_id"] = DEVICE_ID;
  doc["device_type"] = "soil_moisture";
  doc["moisture_raw"] = moistureRaw;
  doc["moisture_percent"] = moisturePercent;
  doc["soil_status"] = soilDry ? "DRY" : "WET";
  doc["uptime_ms"] = millis();

  char payload[256];
  size_t length = serializeJson(doc, payload, sizeof(payload));

  if (mqttClient.publish(telemetryTopic.c_str(), (const uint8_t*)payload, length, false)) {
    Serial.println("MQTT telemetry published");
  } else {
    Serial.println("MQTT telemetry publish failed");
  }
}

void publishAck(const char* commandId, const char* command,
                const char* status, const char* detail) {
  if (!mqttClient.connected()) return;

  JsonDocument doc;
  doc["command_id"] = commandId;
  doc["command"] = command;
  doc["status"] = status;
  doc["detail"] = detail;

  char payload[256];
  size_t length = serializeJson(doc, payload, sizeof(payload));
  mqttClient.publish(ackTopic.c_str(), (const uint8_t*)payload, length, false);
}

void mqttCallback(char* topic, byte* payload, unsigned int length) {
  if (String(topic) != commandTopic) return;

  JsonDocument doc;
  DeserializationError error = deserializeJson(doc, payload, length);
  if (error) {
    Serial.println("Rejected malformed MQTT command JSON");
    return;
  }

  const char* command = doc["command"] | "";
  const char* commandId = doc["command_id"] | "";

  if (strcmp(command, "set_threshold") == 0) {
    int newThreshold = doc["value"] | -1;

    if (newThreshold < 0 || newThreshold > 4095) {
      publishAck(commandId, command, "rejected", "value must be 0..4095");
      return;
    }

    moistureThreshold = newThreshold;
    readSensor();
    publishState();
    publishTelemetry();
    publishAck(commandId, command, "executed", "threshold updated");
    Serial.printf("Threshold changed to %d\n", moistureThreshold);
    return;
  }

  if (strcmp(command, "request_reading") == 0) {
    readSensor();
    publishTelemetry();
    publishAck(commandId, command, "executed", "reading published");
    return;
  }

  publishAck(commandId, command, "rejected", "unknown command");
}

void connectWiFiIfNeeded() {
  if (WiFi.status() == WL_CONNECTED) {
    if (!wifiStarted || WiFi.localIP().toString().length() > 0) {
      static bool connectionReported = false;

      if (!connectionReported) {
        Serial.println("Wi-Fi connected!");
        Serial.print("ESP32 IP: ");
        Serial.println(WiFi.localIP());
        connectionReported = true;
      }
    }
    return;
  }

  unsigned long now = millis();

  // Start Wi-Fi only once initially.
  if (!wifiStarted) {
    Serial.println("Starting Wi-Fi connection...");
    WiFi.mode(WIFI_STA);
   WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
lastWiFiAttemptMs = now;
wifiStarted = true;

Serial.print("Connecting to hotspot: ");
Serial.println(WIFI_SSID);

return;
  }

  // Don't restart Wi-Fi while the ESP32 is still connecting.
  if (now - lastWiFiAttemptMs < 15000) {
    return;
  }

  // Retry after the connection attempt has timed out.
  Serial.println("Wi-Fi connection timed out. Retrying...");

  WiFi.disconnect();
  delay(100);

  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  lastWiFiAttemptMs = millis();
}

void connectMqttIfNeeded() {
  if (WiFi.status() != WL_CONNECTED || mqttClient.connected()) return;

  unsigned long now = millis();
  if (now - lastMqttAttemptMs < MQTT_RETRY_INTERVAL_MS) return;
  lastMqttAttemptMs = now;

  Serial.print("Connecting to MQTT at ");
  Serial.println(MQTT_SERVER);

  // Broker publishes retained "offline" if this device disconnects unexpectedly.
  bool connected = mqttClient.connect(
    DEVICE_ID,
    MQTT_USERNAME,
    MQTT_PASSWORD,
    availabilityTopic.c_str(),
    1,
    true,
    "offline"
  );

  if (connected) {
    Serial.println("MQTT connected");
    mqttClient.publish(availabilityTopic.c_str(), "online", true);
    mqttClient.subscribe(commandTopic.c_str(), 1);
    publishState();
  } else {
    Serial.printf("MQTT connection failed, state=%d\n", mqttClient.state());
  }
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);
delay(500);

Serial.println("\nScanning for Wi-Fi networks...");
int networks = WiFi.scanNetworks();

Serial.printf("Networks found: %d\n", networks);

for (int i = 0; i < networks; i++) {
  Serial.printf(
    "SSID: %s | RSSI: %d | Channel: %d\n",
    WiFi.SSID(i).c_str(),
    WiFi.RSSI(i),
    WiFi.channel(i)
  );
}

WiFi.scanDelete();
Serial.println("Wi-Fi scan complete.");

  pinMode(RED_LED, OUTPUT);
  pinMode(GREEN_LED, OUTPUT);
  digitalWrite(RED_LED, LOW);
  digitalWrite(GREEN_LED, LOW);

  analogReadResolution(12);
  analogSetPinAttenuation(SENSOR_PIN, ADC_11db);

  buildTopics();

  mqttClient.setServer(MQTT_SERVER, MQTT_PORT);
  mqttClient.setCallback(mqttCallback);
  mqttClient.setKeepAlive(30);
  mqttClient.setSocketTimeout(5);
  mqttClient.setBufferSize(512);

  readSensor();
}

void loop() {
  connectWiFiIfNeeded();

  if (WiFi.status() == WL_CONNECTED) {
    connectMqttIfNeeded();
  }

  if (mqttClient.connected()) {
    mqttClient.loop();
  }

  unsigned long now = millis();
  if (now - lastPublishMs >= PUBLISH_INTERVAL_MS) {
    lastPublishMs = now;
    readSensor();
    publishTelemetry();
  }

  delay(2);
}
