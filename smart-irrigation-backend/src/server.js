require("dotenv").config();

const express = require("express");
const cors = require("cors");
const http = require("http");
const mqtt = require("mqtt");
const { Server } = require("socket.io");
const { Pool } = require("pg");
const { randomUUID } = require("crypto");

const required = ["MQTT_URL", "MQTT_USERNAME", "MQTT_PASSWORD", "DATABASE_URL"];
for (const key of required) {
  if (!process.env[key]) throw new Error(`Missing required environment variable: ${key}`);
}

const app = express();
const server = http.createServer(app);
const allowedOrigin = process.env.CORS_ORIGIN || "http://localhost:5173";
const io = new Server(server, { cors: { origin: allowedOrigin } });

app.use(cors({ origin: allowedOrigin }));
app.use(express.json({ limit: "32kb" }));

const pool = new Pool({ connectionString: process.env.DATABASE_URL });
const mqttClient = mqtt.connect(process.env.MQTT_URL, {
  username: process.env.MQTT_USERNAME,
  password: process.env.MQTT_PASSWORD,
  clientId: `irrigation_backend_${process.pid}`,
  reconnectPeriod: 3000,
  connectTimeout: 10000
});

const liveDevices = new Map();

async function initDb() {
  await pool.query(`
    CREATE TABLE IF NOT EXISTS devices (
      device_id TEXT PRIMARY KEY,
      online BOOLEAN NOT NULL DEFAULT FALSE,
      state JSONB,
      last_seen TIMESTAMPTZ,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS readings (
      id BIGSERIAL PRIMARY KEY,
      device_id TEXT NOT NULL,
      moisture_raw INTEGER,
      moisture_percent DOUBLE PRECISION,
      soil_status TEXT,
      uptime_ms BIGINT,
      received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      payload JSONB NOT NULL
    );
    CREATE INDEX IF NOT EXISTS readings_device_time_idx
      ON readings (device_id, received_at DESC);
    CREATE TABLE IF NOT EXISTS command_acks (
      command_id UUID PRIMARY KEY,
      device_id TEXT NOT NULL,
      command TEXT NOT NULL,
      status TEXT NOT NULL,
      detail JSONB,
      received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
  `);
}

function deviceTopic(deviceId, suffix) {
  return `smart-irrigation/devices/${deviceId}/${suffix}`;
}

function validDeviceId(id) {
  return typeof id === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(id);
}

async function upsertAvailability(deviceId, online) {
  await pool.query(
    `INSERT INTO devices(device_id, online, last_seen, updated_at)
     VALUES ($1, $2, CASE WHEN $2 THEN NOW() ELSE NULL END, NOW())
     ON CONFLICT(device_id) DO UPDATE
     SET online = EXCLUDED.online,
         last_seen = CASE WHEN EXCLUDED.online THEN NOW() ELSE devices.last_seen END,
         updated_at = NOW()`,
    [deviceId, online]
  );
  const event = { device_id: deviceId, online };
  liveDevices.set(deviceId, { ...(liveDevices.get(deviceId) || {}), ...event });
  io.emit("device_availability", event);
}

mqttClient.on("connect", () => {
  console.log("Connected to MQTT broker");
  mqttClient.subscribe("smart-irrigation/devices/+/telemetry", { qos: 1 });
  mqttClient.subscribe("smart-irrigation/devices/+/availability", { qos: 1 });
  mqttClient.subscribe("smart-irrigation/devices/+/state", { qos: 1 });
  mqttClient.subscribe("smart-irrigation/devices/+/ack", { qos: 1 });
});

mqttClient.on("reconnect", () => console.log("Reconnecting to MQTT broker..."));
mqttClient.on("error", (err) => console.error("MQTT error:", err.message));

mqttClient.on("message", async (topic, message) => {
  try {
    const parts = topic.split("/");
    if (parts.length !== 4 || parts[0] !== "smart-irrigation" || parts[1] !== "devices") return;
    const deviceId = parts[2];
    const type = parts[3];
    if (!validDeviceId(deviceId)) return;

    if (type === "availability") {
      const online = message.toString() === "online";
      await upsertAvailability(deviceId, online);
      return;
    }

    const data = JSON.parse(message.toString());

    if (type === "telemetry") {
      const raw = Number(data.moisture_raw);
      const percent = Number(data.moisture_percent);
      if (!Number.isFinite(raw) || raw < 0 || raw > 4095 ||
          !Number.isFinite(percent) || percent < 0 || percent > 100) {
        console.warn("Rejected invalid telemetry from", deviceId);
        return;
      }

      const receivedAt = new Date().toISOString();
      const reading = {
        ...data,
        device_id: deviceId,
        received_at: receivedAt
      };

      await pool.query(
        `INSERT INTO readings
         (device_id, moisture_raw, moisture_percent, soil_status, uptime_ms, payload)
         VALUES ($1, $2, $3, $4, $5, $6)`,
        [deviceId, raw, percent, String(data.soil_status || "UNKNOWN"),
         Number.isFinite(Number(data.uptime_ms)) ? Number(data.uptime_ms) : null,
         JSON.stringify(reading)]
      );

      await pool.query(
        `INSERT INTO devices(device_id, online, last_seen, updated_at)
         VALUES ($1, TRUE, NOW(), NOW())
         ON CONFLICT(device_id) DO UPDATE
         SET online = TRUE, last_seen = NOW(), updated_at = NOW()`,
        [deviceId]
      );

      liveDevices.set(deviceId, {
        ...(liveDevices.get(deviceId) || {}),
        device_id: deviceId,
        online: true,
        latest: reading
      });
      io.emit("sensor_update", reading);
      return;
    }

    if (type === "state") {
      await pool.query(
        `INSERT INTO devices(device_id, state, updated_at)
         VALUES ($1, $2, NOW())
         ON CONFLICT(device_id) DO UPDATE
         SET state = EXCLUDED.state, updated_at = NOW()`,
        [deviceId, JSON.stringify(data)]
      );
      liveDevices.set(deviceId, {
        ...(liveDevices.get(deviceId) || {}),
        device_id: deviceId,
        state: data
      });
      io.emit("device_state", { device_id: deviceId, state: data });
      return;
    }

    if (type === "ack") {
      if (!data.command_id || !data.command || !data.status) return;
      await pool.query(
        `INSERT INTO command_acks(command_id, device_id, command, status, detail)
         VALUES ($1, $2, $3, $4, $5)
         ON CONFLICT(command_id) DO NOTHING`,
        [data.command_id, deviceId, data.command, data.status, JSON.stringify(data)]
      );
      io.emit("command_ack", { device_id: deviceId, ...data });
    }
  } catch (err) {
    console.error("Failed processing MQTT message:", err.message);
  }
});

app.get("/api/health", async (_req, res) => {
  let databaseConnected = false;
  try {
    await pool.query("SELECT 1");
    databaseConnected = true;
  } catch (_) {}
  res.status(databaseConnected && mqttClient.connected ? 200 : 503).json({
    status: databaseConnected && mqttClient.connected ? "ok" : "degraded",
    mqtt_connected: mqttClient.connected,
    database_connected: databaseConnected
  });
});

app.get("/api/devices", async (_req, res, next) => {
  try {
    const result = await pool.query(
      `SELECT d.device_id, d.online, d.state, d.last_seen, d.updated_at,
        (SELECT payload FROM readings r WHERE r.device_id=d.device_id
         ORDER BY received_at DESC LIMIT 1) AS latest
       FROM devices d ORDER BY d.device_id`
    );
    res.json(result.rows);
  } catch (err) { next(err); }
});

app.get("/api/devices/:id", async (req, res, next) => {
  try {
    const id = req.params.id;
    if (!validDeviceId(id)) return res.status(400).json({ error: "Invalid device ID" });
    const result = await pool.query("SELECT * FROM devices WHERE device_id=$1", [id]);
    if (!result.rowCount) return res.status(404).json({ error: "Device not found" });
    const latest = await pool.query(
      "SELECT payload FROM readings WHERE device_id=$1 ORDER BY received_at DESC LIMIT 1", [id]
    );
    res.json({ ...result.rows[0], latest: latest.rows[0]?.payload || null });
  } catch (err) { next(err); }
});

app.get("/api/devices/:id/latest", async (req, res, next) => {
  try {
    const id = req.params.id;
    if (!validDeviceId(id)) return res.status(400).json({ error: "Invalid device ID" });
    const result = await pool.query(
      "SELECT payload FROM readings WHERE device_id=$1 ORDER BY received_at DESC LIMIT 1", [id]
    );
    if (!result.rowCount) return res.status(404).json({ error: "No readings found" });
    res.json(result.rows[0].payload);
  } catch (err) { next(err); }
});

app.get("/api/devices/:id/history", async (req, res, next) => {
  try {
    const id = req.params.id;
    if (!validDeviceId(id)) return res.status(400).json({ error: "Invalid device ID" });
    const limit = Math.min(Math.max(parseInt(req.query.limit || "100", 10) || 100, 1), 1000);
    const result = await pool.query(
      `SELECT id, device_id, moisture_raw, moisture_percent, soil_status, received_at, payload
       FROM readings WHERE device_id=$1 ORDER BY received_at DESC LIMIT $2`,
      [id, limit]
    );
    res.json(result.rows.reverse());
  } catch (err) { next(err); }
});

app.post("/api/devices/:id/command", (req, res, next) => {
  const id = req.params.id;
  if (!validDeviceId(id)) return res.status(400).json({ error: "Invalid device ID" });
  const { command, value } = req.body || {};
  const allowed = ["set_threshold", "request_reading"];
  if (!allowed.includes(command)) return res.status(400).json({ error: "Unsupported command" });
  if (command === "set_threshold" &&
      (!Number.isInteger(value) || value < 0 || value > 4095)) {
    return res.status(400).json({ error: "value must be an integer from 0 to 4095" });
  }
  if (!mqttClient.connected) return res.status(503).json({ error: "MQTT broker unavailable" });

  const commandId = randomUUID();
  const payload = {
    command_id: commandId,
    command,
    ...(command === "set_threshold" ? { value } : {})
  };

  mqttClient.publish(deviceTopic(id, "command"), JSON.stringify(payload), { qos: 1 }, (err) => {
    if (err) return next(err);
    res.status(202).json({
      accepted: true,
      device_id: id,
      command_id: commandId,
      message: "Command published; check command_ack for execution result."
    });
  });
});

app.get("/api/commands/:commandId", async (req, res, next) => {
  try {
    const result = await pool.query(
      "SELECT * FROM command_acks WHERE command_id=$1",
      [req.params.commandId]
    );
    if (!result.rowCount) return res.status(404).json({ status: "pending_or_not_found" });
    res.json(result.rows[0]);
  } catch (err) { next(err); }
});

io.on("connection", async (socket) => {
  socket.emit("initial_devices", Array.from(liveDevices.values()));
  try {
    const result = await pool.query(
      `SELECT d.device_id, d.online, d.state,
        (SELECT payload FROM readings r WHERE r.device_id=d.device_id
         ORDER BY received_at DESC LIMIT 1) AS latest
       FROM devices d`
    );
    socket.emit("initial_devices", result.rows);
  } catch (err) {
    console.error("Could not send initial device list:", err.message);
  }
});

app.use((err, _req, res, _next) => {
  console.error(err);
  res.status(500).json({ error: "Internal server error" });
});

const port = Number(process.env.PORT || 3000);

initDb().then(() => {
  server.listen(port, () => console.log(`Smart Irrigation API listening on http://localhost:${port}`));
}).catch((err) => {
  console.error("Database initialization failed:", err);
  process.exit(1);
});

async function shutdown() {
  console.log("Shutting down...");
  mqttClient.end(true);
  io.close();
  server.close();
  await pool.end();
  process.exit(0);
}
process.on("SIGINT", shutdown);
process.on("SIGTERM", shutdown);
