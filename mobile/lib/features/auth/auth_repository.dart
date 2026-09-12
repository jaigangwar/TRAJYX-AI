import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../core/network/api_client.dart';
import 'auth_models.dart';

/// Session persistence and the API calls that create one.
///
/// The token is held in platform secure storage — the Android Keystore — not
/// in SharedPreferences. A bearer token in cleartext preferences is readable
/// by anything with filesystem access on a rooted device, and this token
/// grants access to road-safety data for the account that owns it.
class AuthRepository {
  AuthRepository({required ApiClient client, FlutterSecureStorage? storage})
      : _client = client,
        _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  final ApiClient _client;
  final FlutterSecureStorage _storage;

  static const _sessionKey = 'trajyx.session';

  /// Read the stored session, or null when there is none or it is unusable.
  Future<AuthSession?> readStoredSession() async {
    String? raw;
    try {
      raw = await _storage.read(key: _sessionKey);
    } on Exception {
      // Keystore unavailable (a rare OEM issue). Treat as signed out rather
      // than crashing the app on launch.
      return null;
    }
    if (raw == null) return null;

    try {
      final session = AuthSession.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      if (session.isExpired) {
        await clearSession();
        return null;
      }
      return session;
    } on Exception {
      // Corrupt or from an older shape: discard rather than guess.
      await clearSession();
      return null;
    }
  }

  Future<void> saveSession(AuthSession session) async {
    try {
      await _storage.write(key: _sessionKey, value: jsonEncode(session.toJson()));
    } on Exception {
      // The session still works for this launch; it just will not persist.
    }
  }

  Future<void> clearSession() async {
    try {
      await _storage.delete(key: _sessionKey);
    } on Exception {
      // Nothing further to do.
    }
  }

  /// Exchange credentials for a session.
  ///
  /// Throws [ApiException] on bad credentials (401) or a suspended account
  /// (403), which the UI renders as-is — the API's wording is deliberately
  /// non-revealing about whether an address exists.
  Future<AuthSession> signIn({required String email, required String password}) async {
    final json = await _client.postJson(
      '/auth/login',
      body: {'email': email.trim(), 'password': password},
      anonymous: true,
    );

    final expiresIn = (json['expires_in'] as num?)?.toInt() ?? 3600;
    return AuthSession(
      token: json['access_token'] as String,
      user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
      expiresAt: DateTime.now().add(Duration(seconds: expiresIn)),
    );
  }

  /// Re-read the profile from the API.
  ///
  /// Called on every launch with a stored token. The role that gates the app
  /// therefore comes from the server, not from the stored copy, so editing
  /// stored data grants nothing.
  Future<AuthUser> fetchProfile() async {
    final json = await _client.getJson('/auth/me');
    return AuthUser.fromJson(json);
  }

  /// Register a driver account. The API fixes the role to DRIVER.
  Future<AuthUser> registerDriver({
    required String email,
    required String password,
    String? displayName,
  }) async {
    final json = await _client.postJson(
      '/auth/register',
      body: {
        'email': email.trim(),
        'password': password,
        if (displayName != null && displayName.isNotEmpty) 'display_name': displayName,
      },
      anonymous: true,
    );
    return AuthUser.fromJson(json);
  }

  Future<void> signOut() async {
    try {
      await _client.postJson('/auth/logout');
    } on ApiException {
      // The server revokes what it can; the local session must end regardless.
    }
    await clearSession();
  }
}
