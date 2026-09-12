/// Build-time configuration for the driver app.
///
/// Values come from `--dart-define`, so the same source builds against a local
/// backend, staging or production without code edits:
///
///   flutter run --dart-define=TRAJYX_API_BASE_URL=http://10.0.2.2:8000
///
/// `10.0.2.2` is the host machine as seen from the Android emulator; on a
/// physical device use the host's LAN address.
abstract final class AppConfig {
  static const String apiBaseUrl = String.fromEnvironment(
    'TRAJYX_API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static const String apiPrefix = String.fromEnvironment(
    'TRAJYX_API_PREFIX',
    defaultValue: '/api/v1',
  );

  /// Firebase web/Android API key. Empty means the local development auth path.
  static const String firebaseApiKey = String.fromEnvironment('TRAJYX_FIREBASE_API_KEY');

  static const String firebaseProjectId = String.fromEnvironment('TRAJYX_FIREBASE_PROJECT_ID');

  /// Fully-qualified API root, e.g. `http://10.0.2.2:8000/api/v1`.
  static String get apiRoot => '$apiBaseUrl$apiPrefix';

  static bool get firebaseConfigured => firebaseApiKey.isNotEmpty && firebaseProjectId.isNotEmpty;
}
