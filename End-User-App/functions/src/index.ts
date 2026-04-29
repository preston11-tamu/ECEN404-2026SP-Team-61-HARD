import * as admin from "firebase-admin";
import {onRequest} from "firebase-functions/v2/https";
import {onDocumentCreated} from "firebase-functions/v2/firestore";
import {logger} from "firebase-functions";

// Initialize Firebase Admin SDK
admin.initializeApp();

// Minimum time between alerts per device to prevent duplicate events
const COOLDOWN_MS = 20_000;

/**
 * Receives alert data from edge device via HTTP POST.
 *
 * Validates request, enforces cooldown, and stores alert in Firestore.
 * Returns alert ID if successfully created.
 */
export const publishAlert = onRequest(
  {secrets: ["ALERTS_API_KEY"]},
  async (req, res) => {
    try {
      // Validate HTTP method and API key authentication
      if (req.method !== "POST") {
        res.status(405).send("POST only");
        return;
      }

      const apiKey = req.header("x-api-key");
      const expectedKey = process.env.ALERTS_API_KEY;

      if (!expectedKey || !apiKey || apiKey !== expectedKey) {
        res.status(401).send("Unauthorized");
        return;
      }

      // Log incoming request metadata for debugging and traceability
      logger.info("publishAlert incoming", {
        method: req.method,
        url: req.originalUrl,
        contentType: req.header("content-type"),
        contentLength: req.header("content-length"),
        apiKeyPresent: Boolean(req.header("x-api-key")),
        bodyType: typeof req.body,
        body: req.body,
      });

      // Extract and validate alert fields from request body
      const body = (req.body ?? {}) as Record<string, unknown>;
      const typeRaw = body["type"];
      const roomRaw = body["room"];
      const confidenceRaw = body["confidence"];

      if (typeof typeRaw !== "string" || typeRaw.trim().length === 0) {
        res.status(400).send("Missing or invalid 'type'");
        return;
      }

      if (typeof roomRaw !== "string" || roomRaw.trim().length === 0) {
        res.status(400).send("Missing or invalid 'room'");
        return;
      }

      const type = typeRaw.trim();
      const room = roomRaw.trim();

      // Normalize optional confidence value if provided
      let confidence: number | null = null;
      if (typeof confidenceRaw === "number" && Number.isFinite(confidenceRaw)) {
        confidence = confidenceRaw;
      }

      const nowMs = Date.now();
      const deviceRef = admin.firestore().collection("devices").doc(room);

      let createdAlertId: string | null = null;
      let ignored = false;

      // Use transaction to enforce cooldown and ensure atomic alert creation
      await admin.firestore().runTransaction(async (tx) => {
        const deviceSnap = await tx.get(deviceRef);
        const lastAlertMs = deviceSnap.exists ?
          (deviceSnap.get("lastAlertMs") as number | undefined) :
          undefined;

        // Skip alert creation if within cooldown window
        if (typeof lastAlertMs === "number" &&
          nowMs - lastAlertMs < COOLDOWN_MS
        ) {
          ignored = true;
          return;
        }

        tx.set(
          deviceRef,
          {
            lastAlertMs: nowMs,
            lastAlertAt: admin.firestore.FieldValue.serverTimestamp(),
          },
          {merge: true},
        );

        // Create new alert document in Firestore
        const alertRef = admin.firestore().collection("alerts").doc();
        createdAlertId = alertRef.id;

        // Update device metadata with latest alert timestamp
        tx.set(alertRef, {
          type,
          room,
          confidence,
          acknowledged: false,
          timestamp: admin.firestore.FieldValue.serverTimestamp(),
          notified: false,
          source: "raspi",
          receivedAt: admin.firestore.FieldValue.serverTimestamp(),
        });
      });

      // Return success response if alert was skipped due to cooldown
      if (ignored) {
        logger.info("Alert ignored (cooldown)", {room, type, nowMs});
        res.status(200).json({ok: true, ignored: true});
        return;
      }

      // Return success response with created alert ID
      logger.info("Alert published", {alertId: createdAlertId, room, type});
      res.status(200).json({ok: true, alertId: createdAlertId});
    } catch (err) {
      logger.error("Failed to publish alert", {err});
      res.status(500).send("Failed to publish alert");
    }
  },
);


/**
 * Firestore trigger for new alerts.
 *
 * Sends push notification via FCM and marks alert as notified.
 */
export const notifyOnNewAlert = onDocumentCreated(
  "alerts/{alertId}",
  async (event) => {
    const alertId = event.params.alertId;
    const snap = event.data;

    // Ensure valid Firestore snapshot
    if (!snap) {
      logger.warn("No snapshot data", {alertId: alertId});
      return;
    }

    const alert = snap.data() as Record<string, unknown>;

    // Skip notification if already processed
    if (alert["notified"] === true) {
      logger.info("Alert already notified; skipping", {alertId: alertId});
      return;
    }

    const typeRaw = alert["type"];
    const roomRaw = alert["room"];
    const confidenceRaw = alert["confidence"];

    const type = typeof typeRaw === "string" ? typeRaw : "New Alert";
    const room = typeof roomRaw === "string" ? roomRaw : "Unknown room";

    let confidenceSuffix = "";
    if (typeof confidenceRaw === "number") {
      confidenceSuffix =
        " (conf: " +
        Math.round(confidenceRaw * 100) +
        "%)";
    }

    // Format notification content using alert data
    const title = type;
    const body = "Room: " + room + confidenceSuffix;

    const message: admin.messaging.Message = {
      topic: "alerts",
      notification: {
        title: title,
        body: body,
      },
      data: {
        alertId: alertId,
        room: String(room),
        type: String(type),
      },
      android: {
        priority: "high",
        notification: {
          channelId: "high_importance_channel",
        },
      },
    };

    try {
      // Send notification to subscribed devices via FCM topic
      const response = await admin.messaging().send(message);

      logger.info("Push sent", {alertId: alertId, response: response});

      // Mark alert as notified to prevent duplicate notifications
      await snap.ref.set(
        {
          notified: true,
          notifiedAt: admin.firestore.FieldValue.serverTimestamp(),
        },
        {merge: true},
      );
    } catch (err) {
      logger.error("Failed to send push", {alertId: alertId, err: err});
    }
  },
);

/**
 * HTTP endpoint for receiving device heartbeat updates.
 *
 * Updates lastSeen timestamp in Firestore to track
 * device connectivity and system health.
 */
export const deviceHeartbeat = onRequest(
  {secrets: ["ALERTS_API_KEY"]},
  async (req, res) => {
    try {
      // Validate HTTP method and API key authentication
      if (req.method !== "POST") {
        res.status(405).send("POST only");
        return;
      }

      const apiKey = req.header("x-api-key");
      const expectedKey = process.env.ALERTS_API_KEY;

      if (!expectedKey || !apiKey || apiKey !== expectedKey) {
        res.status(401).send("Unauthorized");
        return;
      }

      // Log incoming heartbeat request metadata
      logger.info("deviceHeartbeat incomng", {
        method: req.method,
        url: req.originalUrl,
        contentType: req.header("content-type"),
        contentLength: req.header("content-length"),
        apiKeyPresent: Boolean(req.header("x-api-key")),
        bodyType: typeof req.body,
      });

      // Extract and validate device identifier from request body
      const body = (req.body ?? {}) as Record<string, unknown>;
      const deviceIdRaw = body["deviceId"];
      const roomRaw = body["room"];

      logger.warn("Invalid deviceId", {deviceIdRaw: deviceIdRaw});
      if (typeof deviceIdRaw !== "string" || deviceIdRaw.trim().length === 0) {
        res.status(400).send("Missing or invalid 'deviceId'");
        return;
      }

      const deviceId = deviceIdRaw.trim();
      const deviceKey = deviceId.toLowerCase();

      // Construct device status update payload
      const update: Record<string, unknown> = {
        deviceId: deviceId,
        lastSeen: admin.firestore.FieldValue.serverTimestamp(),
        lastSeenMs: Date.now(),
        status: "online",
        source: "raspi",
      };

      if (typeof roomRaw === "string" && roomRaw.trim().length > 0) {
        update["room"] = roomRaw.trim();
      }

      // Update device document with latest heartbeat timestamp
      await admin.firestore().collection("devices").doc(deviceKey).set(
        update,
        {merge: true},
      );

      logger.info("Heartbeat received", {deviceKey: deviceKey});

      res.status(200).json({ok: true});
    } catch (err) {
      logger.error("Failed to record heartbeat", {err: err});
      res.status(500).send("Failed to record heartbeat");
    }
  },
);
