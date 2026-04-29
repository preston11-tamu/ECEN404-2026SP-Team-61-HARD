import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'firebase_options.dart';
import 'package:intl/intl.dart';
import 'package:fl_chart/fl_chart.dart';
import 'dart:async';


final GlobalKey<NavigatorState> navigatorKey = GlobalKey<NavigatorState>();

/// Navigates to the alert detail screen when a notification is tapped.
/// Uses a global navigator key to allow navigation outside widget context.
void handleNotificationNavigation(String? alertId) {
  debugPrint('handleNotificationNavigation called with alertId=$alertId');

  if (alertId == null || alertId.isEmpty) {
    debugPrint('No alertId provided, skipping navigation.');
    return;
  }

  navigatorKey.currentState?.push(
    MaterialPageRoute(
      builder: (_) => AlertDetailByIdScreen(alertId: alertId),
    ),
  );
}






/// Firebase Messaging background handler.
/// Ensures Firebase is initialized before processing background messages.
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // Required to use Firebase in background
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
  debugPrint('FCM background message: ${message.messageId}');
}

/// Global notifications plugin
final FlutterLocalNotificationsPlugin flutterLocalNotificationsPlugin =
    FlutterLocalNotificationsPlugin();

/// Android notification channel for HIGH importance alerts
const AndroidNotificationChannel highImportanceChannel =
    AndroidNotificationChannel(
  'high_importance_channel', // id
  'High Importance Notifications', // name
  description: 'Channel for critical fall detection alerts',
  importance: Importance.high,
);

/// Initializes Firebase, messaging, and notification services,
/// then launches the application.
Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );

  // Set FCM background handler
  FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);

  // Initialize local notifications (Android)
  const AndroidInitializationSettings androidInitSettings =
      AndroidInitializationSettings('@mipmap/ic_launcher');

  const InitializationSettings initSettings =
      InitializationSettings(android: androidInitSettings);

  await flutterLocalNotificationsPlugin.initialize(
  initSettings,
  onDidReceiveNotificationResponse: (NotificationResponse response) {
    final payload = response.payload;
    handleNotificationNavigation(payload);
  },
);


  // Create Android notification channel
  await flutterLocalNotificationsPlugin
      .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin>()
      ?.createNotificationChannel(highImportanceChannel);

  runApp(const MyApp());
}

/// Root widget
class MyApp extends StatefulWidget {
  const MyApp({super.key});

  @override
  State<MyApp> createState() => _MyAppState();
}

class _MyAppState extends State<MyApp> {
  final FirebaseMessaging _messaging = FirebaseMessaging.instance;

  @override
  void initState() {
    super.initState();
    _setupPushNotifications();
  }

/// Configures Firebase Cloud Messaging:
/// Requests notification permissions
/// Subscribes device to alert topic
/// Handles foreground messages
/// Handles notification taps from background/terminated states
  Future<void> _setupPushNotifications() async {
  final settings = await _messaging.requestPermission(
    alert: true,
    badge: true,
    sound: true,
  );

  await FirebaseMessaging.instance.subscribeToTopic('alerts');

  debugPrint('User granted permission: ${settings.authorizationStatus}');

  final token = await _messaging.getToken();
  debugPrint('FCM token: $token');

  // Foreground messages 
  FirebaseMessaging.onMessage.listen((RemoteMessage message) {
    debugPrint('Received foreground FCM message: ${message.messageId}');
    _showLocalNotificationFromMessage(message);
  });

  // When notification tapped and opens the app from BACKGROUND
  FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
  debugPrint(
      'Notification opened app from background: ${message.messageId}, data: ${message.data}');
  final alertId = message.data['alertId'] as String?;
  handleNotificationNavigation(alertId);
});

final initialMessage = await _messaging.getInitialMessage();
if (initialMessage != null) {
  debugPrint(
      'App opened from terminated state via notification: ${initialMessage.messageId}, data: ${initialMessage.data}');
  final alertId = initialMessage.data['alertId'] as String?;
  handleNotificationNavigation(alertId);
}
}

/// Displays a local notification based on an incoming FCM message.
/// Extracts alertId from message data for navigation on tap.
  void _showLocalNotificationFromMessage(RemoteMessage message) {
  final notification = message.notification;
  final android = message.notification?.android;

  if (notification == null || android == null) return;

  // Expecting backend / console to include: data: { "alertId": "<docId>" }
  final alertId = message.data['alertId'] as String?;

  flutterLocalNotificationsPlugin.show(
    notification.hashCode,
    notification.title ?? 'New Alert',
    notification.body ?? 'Tap to view details',
    NotificationDetails(
      android: AndroidNotificationDetails(
        highImportanceChannel.id,
        highImportanceChannel.name,
        channelDescription: highImportanceChannel.description,
        importance: Importance.high,
        priority: Priority.high,
        icon: '@mipmap/ic_launcher',
      ),
    ),
    // Payload used when user taps the notification
    payload: alertId,
  );
}


  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'HARD Alerts',
      debugShowCheckedModeBanner: false,
      navigatorKey: navigatorKey,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      home: const AuthGate(),
    );
  }
}


/// Determines application entry point based on authentication state.
/// Routes to login screen or main application.
class AuthGate extends StatelessWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<User?>(
      stream: FirebaseAuth.instance.authStateChanges(),
      builder: (context, snapshot) {
        // Loading
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        // Not logged in
        if (!snapshot.hasData) {
          return const LoginScreen();
        }

        // Logged in
        return const HomeScreen();
      },
    );
  }
}

/// Login Screen
class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final TextEditingController _emailCtrl = TextEditingController();
  final TextEditingController _passwordCtrl = TextEditingController();

  bool _isLoading = false;
  String? _error;

/// Attempts user authentication using Firebase Authentication.
/// Updates UI state based on success or failure.
  Future<void> _login() async {
    if (!_formKey.currentState!.validate()) return;

    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      await FirebaseAuth.instance.signInWithEmailAndPassword(
        email: _emailCtrl.text.trim(),
        password: _passwordCtrl.text.trim(),
      );
    } on FirebaseAuthException catch (e) {
      setState(() {
        _error = e.message ?? 'Login failed';
      });
    } catch (e) {
      setState(() {
        _error = 'Unexpected error: $e';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _emailCtrl.dispose();
    _passwordCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('HARD Alerts - Login'),
      ),
      body: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 400),
            child: Form(
              key: _formKey,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Image.asset(
                    'assets/icon.png',
                    height: 200,
                  ),
                  const Text(
                    'Sign in to view alerts',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 24),
                  TextFormField(
                    controller: _emailCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Email',
                      border: OutlineInputBorder(),
                    ),
                    keyboardType: TextInputType.emailAddress,
                    validator: (value) {
                      if (value == null || value.trim().isEmpty) {
                        return 'Enter your email';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  TextFormField(
                    controller: _passwordCtrl,
                    decoration: const InputDecoration(
                      labelText: 'Password',
                      border: OutlineInputBorder(),
                    ),
                    obscureText: true,
                    validator: (value) {
                      if (value == null || value.isEmpty) {
                        return 'Enter your password';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 16),
                  if (_error != null) ...[
                    Text(
                      _error!,
                      style: const TextStyle(color: Colors.red),
                    ),
                    const SizedBox(height: 8),
                  ],
                  SizedBox(
                    width: double.infinity,
                    child: FilledButton(
                      onPressed: _isLoading ? null : _login,
                      child: _isLoading
                          ? const SizedBox(
                              height: 20,
                              width: 20,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Text('Sign In'),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Displays device connectivity status based on last heartbeat timestamp.
/// Uses Firestore stream to determine online/offline state.
class DeviceStatusIndicator extends StatefulWidget {
  const DeviceStatusIndicator({super.key});

  @override
  State<DeviceStatusIndicator> createState() => _DeviceStatusIndicatorState();
}

class _DeviceStatusIndicatorState extends State<DeviceStatusIndicator> {
  Timer? _timer;

  @override
  void initState() {
    super.initState();

    _timer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        setState(() {});
      }
    });
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  String _formatAgo(int diffSec) {
    if (diffSec < 60) {
      return "${diffSec}s ago";
    }

    final mins = diffSec ~/ 60;
    final secs = diffSec % 60;

    if (mins < 60) {
      return "${mins}m ${secs}s ago";
    }

    final hours = mins ~/ 60;
    final remMins = mins % 60;
    return "${hours}h ${remMins}m ago";
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
      stream: FirebaseFirestore.instance
          .collection('devices')
          .doc('pi on')
          .snapshots(),
      builder: (context, snapshot) {
        bool isOnline = false;
        String lastSeenText = "No data";

        if (snapshot.hasData && snapshot.data!.exists) {
          final data = snapshot.data!.data()!;
          final lastSeen = data['lastSeen'] as Timestamp?;

          if (lastSeen != null) {
            final diffSec =
                DateTime.now().difference(lastSeen.toDate()).inSeconds;

            isOnline = diffSec < 90;
            lastSeenText = _formatAgo(diffSec);
          }
        }

        return Padding(
          padding: const EdgeInsets.only(right: 12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                Icons.circle,
                size: 12,
                color: isOnline ? Colors.green : Colors.red,
              ),
              const SizedBox(width: 6),
              Text(
                lastSeenText,
                style: const TextStyle(fontSize: 12),
              ),
            ],
          ),
        );
      },
    );
  }
}

/// Home Screen (Alert List)
String formatTimestamp(Timestamp? ts) {
  if (ts == null) return 'Unknown time';
  final dt = ts.toDate().toLocal();
  return DateFormat('MMM d, yyyy h:mm a').format(dt);
}

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

/// Returns a real-time stream of alerts filtered by acknowledgment status.
/// Data is ordered by most recent timestamp.
  Stream<QuerySnapshot<Map<String, dynamic>>> _alertsStream({
    required bool acknowledged,
  }) {
    return FirebaseFirestore.instance
        .collection('alerts')
        .where('acknowledged', isEqualTo: acknowledged)
        .orderBy('timestamp', descending: true)
        .snapshots();
  }

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3, // 3 tabs
      child: Scaffold(
        appBar: AppBar(
          title: const Text('HARD Alerts'),
          actions: [
            const DeviceStatusIndicator(),
              IconButton(
              icon: const Icon(Icons.settings),
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => const SettingsScreen(),
                  ),
                );
              },
            ),
          ],
        ),
        body: const TabBarView(
          children: [
            _AlertsList(acknowledged: false),
            _AlertsList(acknowledged: true),
            LogisticsTab(), 
          ],
        ),
      ),
    );
  }
}




/// Displays detailed information for a single alert.
/// Supports acknowledgment and updates Firestore accordingly.
class AlertDetailScreen extends StatefulWidget {
  final String alertId;
  final Map<String, dynamic> data;

  const AlertDetailScreen({
    super.key,
    required this.alertId,
    required this.data,
  });

  @override
  State<AlertDetailScreen> createState() => _AlertDetailScreenState();
}

class _AlertDetailScreenState extends State<AlertDetailScreen> {
  bool _updating = false;
  late Map<String, dynamic> _data;

  @override
  void initState() {
    super.initState();
    // Makes mutable copy, can update UI after acknowledging
    _data = Map<String, dynamic>.from(widget.data);
  }

/// Marks the alert as acknowledged and records user + timestamp.
  Future<void> _acknowledgeAlert() async {
    setState(() {
      _updating = true;
    });

    try {
      final user = FirebaseAuth.instance.currentUser;

      await FirebaseFirestore.instance
          .collection('alerts')
          .doc(widget.alertId)
          .update({
        'acknowledged': true,
        'acknowledgedBy': user?.email ?? 'unknown',
        'acknowledgedAt': FieldValue.serverTimestamp(),
      });

      if (!mounted) return;

      // Update local state, UI reflects change immediately
      setState(() {
        _data['acknowledged'] = true;
        _data['acknowledgedBy'] = user?.email ?? 'unknown';
        // Firestore fill in 'acknowledgedAt'; user sees it
        // next time detail opened or from logistics
      });

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Alert acknowledged')),
      );
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Failed to acknowledge: $e')),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _updating = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final data = _data;

    final timestamp = data['timestamp'] as Timestamp?;
    final timeString = timestamp != null
        ? timestamp.toDate().toLocal().toString()
        : 'Unknown time';

    final acknowledged = data['acknowledged'] as bool? ?? false;
    final acknowledgedBy = data['acknowledgedBy'] as String?;
    final ackTs = data['acknowledgedAt'] as Timestamp?;

    String? ackTimeString;
    if (ackTs != null) {
      ackTimeString = ackTs.toDate().toLocal().toString();
    }

    final alertType = data['type'] as String? ?? 'Alert';
    final room = data['room'] as String? ?? 'Unknown';
    final confidence = data['confidence'];

    return Scaffold(
      appBar: AppBar(
        title: const Text('Alert Details'),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: ListView(
          children: [
            // Title
            Text(
              alertType,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.bold,
                  ),
            ),
            const SizedBox(height: 12),

            // Room
            Row(
              children: [
                const Icon(Icons.room, size: 18),
                const SizedBox(width: 6),
                Text(
                  'Room: $room',
                  style: const TextStyle(fontSize: 16),
                ),
              ],
            ),
            const SizedBox(height: 8),

            // Time
            Row(
              children: [
                const Icon(Icons.access_time, size: 18),
                const SizedBox(width: 6),
                Text(
                  'Time: $timeString',
                  style: const TextStyle(fontSize: 14),
                ),
              ],
            ),
            const SizedBox(height: 8),

            // Confidence
            if (confidence != null) ...[
              Row(
                children: [
                  const Icon(Icons.insights, size: 18),
                  const SizedBox(width: 6),
                  Text(
                    'Confidence: $confidence',
                    style: const TextStyle(fontSize: 14),
                  ),
                ],
              ),
              const SizedBox(height: 16),
            ] else
              const SizedBox(height: 16),

            // Acknowledgement status
            Text(
              'Acknowledged: ${acknowledged ? "Yes" : "No"}',
              style: const TextStyle(fontSize: 16),
            ),
            if (acknowledgedBy != null)
              Text(
                'Acknowledged By: $acknowledgedBy',
                style: const TextStyle(fontSize: 14),
              ),
            if (ackTimeString != null)
              Text(
                'Acknowledged At: $ackTimeString',
                style: const TextStyle(fontSize: 14),
              ),

            const SizedBox(height: 24),

            // Acknowledge button
            if (!acknowledged)
              FilledButton(
                onPressed: _updating ? null : _acknowledgeAlert,
                child: _updating
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Text('Acknowledge Alert'),
              ),
          ],
        ),
      ),
    );
  }
}


/// Loads alert data in real time by document ID.
/// Updates automatically if alert state changes.
class AlertDetailByIdScreen extends StatelessWidget {
  final String alertId;

  const AlertDetailByIdScreen({
    super.key,
    required this.alertId,
  });

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
      stream: FirebaseFirestore.instance
          .collection('alerts')
          .doc(alertId)
          .snapshots(),
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Scaffold(
            appBar: AppBar(title: const Text('Alert Details')),
            body: Center(
              child: Text('Error loading alert: ${snapshot.error}'),
            ),
          );
        }

        if (!snapshot.hasData || !snapshot.data!.exists) {
          return Scaffold(
            appBar: AppBar(title: const Text('Alert Details')),
            body: const Center(
              child: Text('Alert not found'),
            ),
          );
        }

        final data = snapshot.data!.data()!;
        return AlertDetailScreen(alertId: alertId, data: data);
      },
    );
  }
}



/// Displays application settings and Firebase debug information.
/// Provides user sign-out functionality.
class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final user = FirebaseAuth.instance.currentUser;

    // Firebase debug info for project 
    final app = Firebase.app();
    final projectId = app.options.projectId;
    final appId = app.options.appId;
    final senderId = app.options.messagingSenderId;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Settings'),
      ),
      body: ListView(
        children: [
          if (user != null) ...[
            ListTile(
              leading: const Icon(Icons.person),
              title: Text(user.email ?? 'Signed-in user'),
              subtitle: const Text('Currently signed in'),
            ),
            const Divider(),
          ],

          // Debug tile
          ListTile(
            leading: const Icon(Icons.bug_report),
            title: const Text('Firebase debug'),
            subtitle: Text(
              'projectId: $projectId\n'
              'appId: $appId\n'
              'senderId: $senderId',
            ),
          ),
          const Divider(),

          ListTile(
            leading: const Icon(Icons.notifications),
            title: const Text('Alert notifications'),
            subtitle: const Text('Always on (managed by system/FCM)'),
            onTap: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text(
                    'Notification preferences will be configurable in a future update.',
                  ),
                ),
              );
            },
          ),

          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('About'),
            subtitle: const Text('HARD – Human Activity Radar Detection app'),
          ),

          const Divider(),

          ListTile(
            leading: const Icon(Icons.logout, color: Colors.red),
            title: const Text(
              'Sign out',
              style: TextStyle(color: Colors.red),
            ),
            onTap: () async {
              try {
                await FirebaseAuth.instance.signOut();

                if (!context.mounted) return;

                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Signed out')),
                );

                Navigator.of(context).popUntil((route) => route.isFirst);
              } catch (e) {
                if (!context.mounted) return;

                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text('Sign out failed: $e')),
                );
              }
            },
          ),
        ],
      ),
    );
  }
}

/// Displays a list of alerts using a real-time Firestore stream.
/// Separates acknowledged and unacknowledged alerts.
class _AlertsList extends StatelessWidget {
  final bool acknowledged;

  const _AlertsList({required this.acknowledged});

  Stream<QuerySnapshot<Map<String, dynamic>>> _alertStream() {
    return FirebaseFirestore.instance
        .collection('alerts')
        .where('acknowledged', isEqualTo: acknowledged)
        .orderBy('timestamp', descending: true)
        .snapshots();
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
      stream: _alertStream(),
      builder: (context, snapshot) {
        if (snapshot.hasError) {
          return Center(
            child: Text('Error loading alerts: ${snapshot.error}'),
          );
        }

        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(child: CircularProgressIndicator());
        }

        final docs = snapshot.data?.docs ?? [];

        if (docs.isEmpty) {
          if (!acknowledged) {
            // Unacknowledged tab empty
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.check_circle_outline,
                        size: 64, color: Colors.green),
                    SizedBox(height: 16),
                    Text(
                      'No active alerts',
                      style:
                          TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                    ),
                    SizedBox(height: 8),
                    Text(
                      'You\'ll see new alerts here when the system detects an event.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            );
          } else {
            // Acknowledged tab empty
            return const Center(
              child: Padding(
                padding: EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.history, size: 64),
                    SizedBox(height: 16),
                    Text(
                      'No acknowledged alerts yet',
                      style:
                          TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                    ),
                    SizedBox(height: 8),
                    Text(
                      'Once alerts are acknowledged, they will appear here.',
                      textAlign: TextAlign.center,
                    ),
                  ],
                ),
              ),
            );
          }
        }

        return ListView.builder(
          itemCount: docs.length,
          itemBuilder: (context, index) {
            final doc = docs[index];
            final data = doc.data();
            final timestamp = data['timestamp'] as Timestamp?;
            final isAck = data['acknowledged'] as bool? ?? false;
            final alertType = data['type'] as String? ?? 'Alert';

            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              child: Card(
                elevation: 2,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                ),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor:
                        isAck ? Colors.green[100] : Colors.red[100],
                    child: Icon(
                      isAck ? Icons.check : Icons.warning_amber_rounded,
                      color:
                          isAck ? Colors.green[800] : Colors.red[800],
                    ),
                  ),
                  title: Text(
                    alertType,
                    style: const TextStyle(fontWeight: FontWeight.w600),
                  ),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (data['room'] != null)
                        Text('Room: ${data['room']}'),
                      Text(
                        formatTimestamp(timestamp),
                        style: const TextStyle(fontSize: 12),
                      ),
                    ],
                  ),
                  trailing: Container(
                    padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      color: isAck ? Colors.green[50] : Colors.red[50],
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: Text(
                      isAck ? 'ACK' : 'NEW',
                      style: TextStyle(
                        color: isAck
                            ? Colors.green[800]
                            : Colors.red[800],
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      ),
                    ),
                  ),
                  onTap: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (_) => AlertDetailScreen(
                          alertId: doc.id,
                          data: data,
                        ),
                      ),
                    );
                  },
                ),
              ),
            );
          },
        );
      },
    );
  }
}


enum _LogisticsRange {
  day,
  week,
  month,
}

/// Provides aggregated analytics over alert data.
/// Supports selectable time ranges and per-room statistics.
class LogisticsTab extends StatefulWidget {
  const LogisticsTab({super.key});

  @override
  State<LogisticsTab> createState() => _LogisticsTabState();
}

class _LogisticsTabState extends State<LogisticsTab> {
  _LogisticsRange _selectedRange = _LogisticsRange.week;

  Duration _durationForRange(_LogisticsRange range) {
    switch (range) {
      case _LogisticsRange.day:
        return const Duration(days: 1);
      case _LogisticsRange.week:
        return const Duration(days: 7);
      case _LogisticsRange.month:
        return const Duration(days: 30);
    }
  }

  String _labelForRange(_LogisticsRange range) {
    switch (range) {
      case _LogisticsRange.day:
        return 'Last 24 hours';
      case _LogisticsRange.week:
        return 'Last 7 days';
      case _LogisticsRange.month:
        return 'Last 30 days';
    }
  }

  Future<QuerySnapshot<Map<String, dynamic>>> _fetchRecentAlerts() {
    final now = DateTime.now();
    final start = now.subtract(_durationForRange(_selectedRange));

    return FirebaseFirestore.instance
        .collection('alerts')
        .where('timestamp',
            isGreaterThanOrEqualTo: Timestamp.fromDate(start))
        .get();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        // Time range dropdown
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
          child: Row(
            children: [
              const Text(
                'Time range:',
                style: TextStyle(fontWeight: FontWeight.w500),
              ),
              const SizedBox(width: 12),
              DropdownButton<_LogisticsRange>(
                value: _selectedRange,
                items: _LogisticsRange.values.map((range) {
                  return DropdownMenuItem(
                    value: range,
                    child: Text(_labelForRange(range)),
                  );
                }).toList(),
                onChanged: (value) {
                  if (value == null) return;
                  setState(() {
                    _selectedRange = value;
                  });
                },
              ),
            ],
          ),
        ),
        const SizedBox(height: 8),
        Expanded(
          child: FutureBuilder<QuerySnapshot<Map<String, dynamic>>>(
            future: _fetchRecentAlerts(),
            builder: (context, snapshot) {
              if (snapshot.hasError) {
                return Center(
                  child:
                      Text('Error loading logistics: ${snapshot.error}'),
                );
              }

              if (snapshot.connectionState ==
                  ConnectionState.waiting) {
                return const Center(
                    child: CircularProgressIndicator());
              }

              final docs = snapshot.data?.docs ?? [];

              if (docs.isEmpty) {
                return const Center(
                  child: Padding(
                    padding: EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.info_outline, size: 64),
                        SizedBox(height: 16),
                        Text(
                          'No alerts in this time range',
                          style: TextStyle(
                              fontSize: 20,
                              fontWeight: FontWeight.bold),
                        ),
                        SizedBox(height: 8),
                        Text(
                          'Once falls are detected, this page will show activity by room.',
                          textAlign: TextAlign.center,
                        ),
                      ],
                    ),
                  ),
                );
              }

              // Aggregate by room
              final Map<String, _RoomAggregate> roomStats = {};

              for (final doc in docs) {
                final data = doc.data();
                final room =
                    (data['room'] as String?) ?? 'Unknown';
                final ts =
                    (data['timestamp'] as Timestamp?)?.toDate();
                final acknowledged =
                    data['acknowledged'] as bool? ?? false;
                final ackTs =
                    (data['acknowledgedAt'] as Timestamp?)
                        ?.toDate();

                final agg = roomStats.putIfAbsent(
                  room,
                  () => _RoomAggregate(),
                );

                if (ts != null) {
                  agg.count++;
                  if (agg.lastAlert == null ||
                      ts.isAfter(agg.lastAlert!)) {
                    agg.lastAlert = ts;
                  }

                  if (acknowledged && ackTs != null) {
                    agg.responseTimes.add(
                        ackTs.difference(ts));
                  }
                }
              }

              final totalFalls = docs.length;
              String mostActiveRoom = 'N/A';
              int maxCount = 0;

              roomStats.forEach((room, agg) {
                if (agg.count > maxCount) {
                  maxCount = agg.count;
                  mostActiveRoom = room;
                }
              });

              // Sort rooms by activity
              final sortedRooms =
                  roomStats.entries.toList()
                    ..sort((a, b) =>
                        b.value.count.compareTo(a.value.count));

              return SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
                child: Column(
                  crossAxisAlignment:
                      CrossAxisAlignment.start,
                  children: [
                    // Summary cards
                    Row(
                      children: [
                        Expanded(
                          child: Card(
                            elevation: 2,
                            child: Padding(
                              padding:
                                  const EdgeInsets.all(12),
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment
                                        .start,
                                children: [
                                  const Text(
                                    'Total falls',
                                    style: TextStyle(
                                        fontWeight:
                                            FontWeight
                                                .w500),
                                  ),
                                  const SizedBox(
                                      height: 4),
                                  Text(
                                    '$totalFalls',
                                    style:
                                        const TextStyle(
                                      fontSize: 24,
                                      fontWeight:
                                          FontWeight.bold,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Card(
                            elevation: 2,
                            child: Padding(
                              padding:
                                  const EdgeInsets.all(12),
                              child: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment
                                        .start,
                                children: [
                                  const Text(
                                    'Most active room',
                                    style: TextStyle(
                                        fontWeight:
                                            FontWeight
                                                .w500),
                                  ),
                                  const SizedBox(
                                      height: 4),
                                  Text(
                                    mostActiveRoom,
                                    style:
                                        const TextStyle(
                                      fontSize: 16,
                                      fontWeight:
                                          FontWeight.bold,
                                    ),
                                  ),
                                  if (maxCount > 0)
                                    Text(
                                      '$maxCount alert(s)',
                                      style: const TextStyle(
                                          fontSize: 12),
                                    ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),

                    const SizedBox(height: 16),

                    // Bar chart
                    Card(
                      elevation: 2,
                      child: SizedBox(
                        height: 220,
                        child: Padding(
                          padding:
                              const EdgeInsets.all(12.0),
                          child: _buildRoomBarChart(
                              context, sortedRooms),
                        ),
                      ),
                    ),

                    const SizedBox(height: 16),

                    Text(
                      'Rooms by activity',
                      style: Theme.of(context)
                          .textTheme
                          .titleMedium
                          ?.copyWith(
                              fontWeight:
                                  FontWeight.bold),
                    ),
                    const SizedBox(height: 8),

                    ListView.builder(
                      shrinkWrap: true,
                      physics:
                          const NeverScrollableScrollPhysics(),
                      itemCount: sortedRooms.length,
                      itemBuilder: (context, index) {
                        final entry =
                            sortedRooms[index];
                        final room = entry.key;
                        final agg = entry.value;

                        final lastAlertStr =
                            agg.lastAlert != null
                                ? DateFormat(
                                        'MMM d, yyyy h:mm a')
                                    .format(
                                        agg.lastAlert!)
                                : 'Unknown';

                        final avgResponse =
                            agg.averageResponseTime;

                        String avgResponseStr = 'N/A';
                        if (avgResponse != null) {
                          final mins =
                              avgResponse.inMinutes;
                          final secs = avgResponse
                                  .inSeconds %
                              60;
                          if (mins > 0) {
                            avgResponseStr =
                                '${mins}m ${secs}s';
                          } else {
                            avgResponseStr =
                                '${secs}s';
                          }
                        }

                        return Padding(
                          padding:
                              const EdgeInsets.symmetric(
                                  vertical: 4),
                          child: Card(
                            elevation: 1,
                            child: ListTile(
                              title: Text(room),
                              subtitle: Column(
                                crossAxisAlignment:
                                    CrossAxisAlignment
                                        .start,
                                children: [
                                  Text(
                                      'Falls: ${agg.count}'),
                                  Text(
                                      'Last alert: $lastAlertStr'),
                                  Text(
                                      'Avg response: $avgResponseStr'),
                                ],
                              ),
                              onTap: () {
                                Navigator.of(context)
                                    .push(
                                  MaterialPageRoute(
                                    builder: (_) =>
                                        RoomAlertsScreen(
                                      room: room,
                                    ),
                                  ),
                                );
                              },
                            ),
                          ),
                        );
                      },
                    ),
                  ],
                ),
              );
            },
          ),
        ),
      ],
    );
  }

  Widget _buildRoomBarChart(
    BuildContext context,
    List<MapEntry<String, _RoomAggregate>> rooms,
  ) {
    if (rooms.isEmpty) {
      return const Center(
        child: Text('No data to display'),
      );
    }

    return BarChart(
      BarChartData(
        barGroups: List.generate(rooms.length, (index) {
          final count = rooms[index].value.count.toDouble();
          return BarChartGroupData(
            x: index,
            barRods: [
              BarChartRodData(
                toY: count,
                width: 16,
              ),
            ],
          );
        }),
        titlesData: FlTitlesData(
          leftTitles: AxisTitles(
            sideTitles:
                SideTitles(showTitles: true, reservedSize: 28),
          ),
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              reservedSize: 36,
              getTitlesWidget: (value, meta) {
                final index = value.toInt();
                if (index < 0 || index >= rooms.length) {
                  return const SizedBox.shrink();
                }
                final room = rooms[index].key;
                return Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: Text(
                    room,
                    style: const TextStyle(fontSize: 10),
                    overflow: TextOverflow.ellipsis,
                  ),
                );
              },
            ),
          ),
          topTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles:
              const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        gridData: FlGridData(show: true),
        borderData: FlBorderData(show: false),
      ),
    );
  }
}


/// Helper model for storing per-room alert statistics.
class _RoomAggregate {
  int count = 0;
  DateTime? lastAlert;
  final List<Duration> responseTimes = [];

  Duration? get averageResponseTime {
    if (responseTimes.isEmpty) return null;
    final total = responseTimes.fold<Duration>(
      Duration.zero,
      (sum, d) => sum + d,
    );
    return Duration(
      milliseconds:
          (total.inMilliseconds / responseTimes.length).round(),
    );
  }
}

/// Displays all alerts associated with a specific room.
class RoomAlertsScreen extends StatelessWidget {
  final String room;

  const RoomAlertsScreen({super.key, required this.room});

  Stream<QuerySnapshot<Map<String, dynamic>>> _roomAlertsStream() {
    return FirebaseFirestore.instance
        .collection('alerts')
        .where('room', isEqualTo: room)
        .orderBy('timestamp', descending: true)
        .snapshots();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Alerts – $room'),
      ),
      body: StreamBuilder<QuerySnapshot<Map<String, dynamic>>>(
        stream: _roomAlertsStream(),
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return Center(
              child: Text('Error loading alerts: ${snapshot.error}'),
            );
          }

          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }

          final docs = snapshot.data?.docs ?? [];

          if (docs.isEmpty) {
            return const Center(
              child: Text('No alerts for this room yet'),
            );
          }

          return ListView.builder(
            itemCount: docs.length,
            itemBuilder: (context, index) {
              final doc = docs[index];
              final data = doc.data();
              final timestamp =
                  data['timestamp'] as Timestamp?;
              final acknowledged =
                  data['acknowledged'] as bool? ?? false;
              final alertType =
                  data['type'] as String? ?? 'Alert';

              return Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: 12, vertical: 6),
                child: Card(
                  elevation: 2,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: ListTile(
                    leading: CircleAvatar(
                      backgroundColor: acknowledged
                          ? Colors.green[100]
                          : Colors.red[100],
                      child: Icon(
                        acknowledged
                            ? Icons.check
                            : Icons.warning_amber_rounded,
                        color: acknowledged
                            ? Colors.green[800]
                            : Colors.red[800],
                      ),
                    ),
                    title: Text(
                      alertType,
                      style: const TextStyle(
                          fontWeight: FontWeight.w600),
                    ),
                    subtitle: Text(
                      formatTimestamp(timestamp),
                      style: const TextStyle(fontSize: 12),
                    ),
                    trailing: Text(
                      acknowledged ? 'ACK' : 'NEW',
                      style: TextStyle(
                        color: acknowledged
                            ? Colors.green[800]
                            : Colors.red[800],
                        fontWeight: FontWeight.bold,
                        fontSize: 12,
                      ),
                    ),
                    onTap: () {
                      Navigator.of(context).push(
                        MaterialPageRoute(
                          builder: (_) => AlertDetailScreen(
                            alertId: doc.id,
                            data: data,
                          ),
                        ),
                      );
                    },
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
