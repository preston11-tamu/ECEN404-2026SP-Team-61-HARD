# HARD App & Backend Subsystem

This repository contains the mobile application and cloud backend for the HARD system. This subsystem is responsible for receiving detection events from the edge device, storing them in the cloud, and presenting them to the user in real time.

The system uses a Firebase-based, event-driven architecture with a Flutter mobile application.

Data flow:
Edge Device → HTTP Request → Firebase Cloud Function → Firestore → Push Notification (FCM) → Mobile App

The mobile application provides a real-time interface for viewing alerts, acknowledging events, monitoring device status, and viewing basic analytics. Alerts are displayed using Firestore streams, allowing the UI to update automatically without manual refresh. Push notifications are delivered using Firebase Cloud Messaging and support both foreground and background operation.

The backend is implemented using Firebase Cloud Functions. The 'publishAlert' endpoint receives alert data from the edge device, validates the request, applies a cooldown to prevent duplicate alerts, and stores the alert in Firestore. The 'deviceHeartbeat' endpoint updates the device’s last seen timestamp to track connectivity. A Firestore trigger listens for new alerts and sends push notifications to subscribed devices.

Firestore is used as the primary data store. The 'alerts' collection contains alert type, room, confidence, timestamp, and acknowledgment data. The 'devices' collection tracks device status using heartbeat updates.

To run the mobile application:
- Install Flutter SDK
- Run:
  flutter pub get
  flutter run

To run the backend:
- Navigate to the functions directory
- Run:
  npm install
  firebase deploy --only functions

Notes:
- 'node_modules' is not included and must be installed locally
- Firebase configuration is required to run the app
- API keys are handled using environment variables
