import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:trajyx/core/contracts/domain.dart';
import 'package:trajyx/core/network/api_client.dart';
import 'package:trajyx/core/providers.dart';
import 'package:trajyx/core/theme/tokens.dart';
import 'package:trajyx/features/auth/auth_controller.dart';
import 'package:trajyx/features/auth/auth_models.dart';
import 'package:trajyx/features/auth/auth_repository.dart';
import 'package:trajyx/main.dart';

const _healthBody = {
  'status': 'ok',
  'service': 'TRAJYX API',
  'version': '0.1.0',
  'environment': 'test',
  'contract_version': '1.0.0',
  'capabilities': {
    'data_backend': 'local',
    'auth_backend': 'local',
    'storage_backend': 'local',
    'demo_mode': true,
  },
  'warnings': <String>[],
};

Map<String, dynamic> _user({String role = 'DRIVER'}) => {
      'id': 'user-1',
      'email': 'driver@trajyx.local',
      'display_name': 'Dee Driver',
      'role': role,
      'status': 'active',
    };

/// In-memory stand-in for secure storage, so tests do not need a Keystore.
class _FakeAuthRepository extends AuthRepository {
  _FakeAuthRepository({required super.client, AuthSession? initial}) : _session = initial;

  AuthSession? _session;

  @override
  Future<AuthSession?> readStoredSession() async => _session;

  @override
  Future<void> saveSession(AuthSession session) async => _session = session;

  @override
  Future<void> clearSession() async => _session = null;
}

/// Routes requests by URL substring. Unmatched paths fail loudly.
MockClient _mockClient(Map<String, (int, Object)> routes) {
  return MockClient((request) async {
    for (final entry in routes.entries) {
      if (request.url.path.contains(entry.key)) {
        final (status, body) = entry.value;
        return http.Response(
          jsonEncode(body),
          status,
          headers: {'content-type': 'application/json'},
        );
      }
    }
    return http.Response('{"error":{"code":"NOT_FOUND","message":"no stub"}}', 404,
        headers: {'content-type': 'application/json'});
  });
}

Widget _boot({
  required Map<String, (int, Object)> routes,
  AuthSession? storedSession,
}) {
  final client = ApiClient(
    httpClient: _mockClient(routes),
    baseUrl: 'http://test.local/api/v1',
  );

  return ProviderScope(
    overrides: [
      apiClientProvider.overrideWithValue(client),
      authRepositoryProvider.overrideWithValue(
        _FakeAuthRepository(client: client, initial: storedSession),
      ),
    ],
    child: const TrajyxApp(),
  );
}

AuthSession _session({String role = 'DRIVER'}) => AuthSession(
      token: 'test-token',
      user: AuthUser.fromJson(_user(role: role)),
      expiresAt: DateTime.now().add(const Duration(hours: 1)),
    );

void main() {
  group('auth gate', () {
    testWidgets('shows the login screen when no session is stored', (tester) async {
      await tester.pumpWidget(_boot(routes: {'/health': (200, _healthBody)}));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
      expect(find.text('Email address'), findsOneWidget);
    });

    testWidgets('restores a stored session straight into the app', (tester) async {
      await tester.pumpWidget(
        _boot(
          routes: {'/auth/me': (200, _user()), '/health': (200, _healthBody)},
          storedSession: _session(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(NavigationBar), findsOneWidget);
      expect(find.text('Home'), findsWidgets);
    });

    testWidgets('discards a stored session the API rejects', (tester) async {
      await tester.pumpWidget(
        _boot(
          routes: {
            '/auth/me': (401, {'error': {'code': 'UNAUTHENTICATED', 'message': 'Expired.'}}),
            '/health': (200, _healthBody),
          },
          storedSession: _session(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
    });

    testWidgets('keeps a staff account out of the driver app', (tester) async {
      await tester.pumpWidget(
        _boot(
          routes: {
            '/auth/me': (200, _user(role: 'TRAFFIC_OPERATOR')),
            '/health': (200, _healthBody),
          },
          storedSession: _session(role: 'TRAFFIC_OPERATOR'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
      expect(find.textContaining('web console'), findsOneWidget);
    });

    testWidgets('stays signed in when the device is offline', (tester) async {
      // A dead connection on the road must not lock a driver out of cached
      // risk zones, so an unreachable API keeps the stored session.
      final offlineClient = ApiClient(
        // A real SocketException: that is what ApiClient translates into an
        // OFFLINE ApiException, so a stand-in class would not exercise the path.
        httpClient: MockClient((_) async => throw const SocketException('offline')),
        baseUrl: 'http://test.local/api/v1',
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            apiClientProvider.overrideWithValue(offlineClient),
            authRepositoryProvider.overrideWithValue(
              _FakeAuthRepository(client: offlineClient, initial: _session()),
            ),
          ],
          child: const TrajyxApp(),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byType(NavigationBar), findsOneWidget);
    });
  });

  group('sign-in form', () {
    testWidgets('signs in and enters the app', (tester) async {
      await tester.pumpWidget(
        _boot(
          routes: {
            '/auth/login': (
              200,
              {
                'access_token': 'fresh-token',
                'token_type': 'bearer',
                'expires_in': 3600,
                'user': _user(),
              }
            ),
            '/auth/me': (200, _user()),
            '/health': (200, _healthBody),
          },
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextFormField).first, 'driver@trajyx.local');
      await tester.enterText(find.byType(TextFormField).last, 'Driver-Pass-1');
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pumpAndSettle();

      expect(find.byType(NavigationBar), findsOneWidget);
    });

    testWidgets('shows the API message on a failed sign-in', (tester) async {
      await tester.pumpWidget(
        _boot(
          routes: {
            '/auth/login': (
              401,
              {
                'error': {
                  'code': 'UNAUTHENTICATED',
                  'message': 'Incorrect email address or password.',
                }
              }
            ),
            '/health': (200, _healthBody),
          },
        ),
      );
      await tester.pumpAndSettle();

      await tester.enterText(find.byType(TextFormField).first, 'driver@trajyx.local');
      await tester.enterText(find.byType(TextFormField).last, 'wrong');
      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pumpAndSettle();

      expect(find.text('Incorrect email address or password.'), findsOneWidget);
      expect(find.byType(NavigationBar), findsNothing);
    });

    testWidgets('validates empty fields before calling the API', (tester) async {
      await tester.pumpWidget(_boot(routes: {'/health': (200, _healthBody)}));
      await tester.pumpAndSettle();

      await tester.tap(find.widgetWithText(FilledButton, 'Sign in'));
      await tester.pumpAndSettle();

      expect(find.text('Enter your email address'), findsOneWidget);
      expect(find.text('Enter your password'), findsOneWidget);
    });

    testWidgets('offers driver registration', (tester) async {
      await tester.pumpWidget(_boot(routes: {'/health': (200, _healthBody)}));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Create a driver account'));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Create account'), findsOneWidget);
      expect(find.text('Name (optional)'), findsOneWidget);
    });
  });

  group('profile', () {
    testWidgets('shows the signed-in account and can sign out', (tester) async {
      await tester.pumpWidget(
        _boot(
          routes: {
            '/auth/me': (200, _user()),
            '/auth/logout': (200, {'ok': true}),
            '/health': (200, _healthBody),
          },
          storedSession: _session(),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Profile'));
      await tester.pumpAndSettle();

      expect(find.text('Dee Driver'), findsOneWidget);
      expect(find.text('driver@trajyx.local'), findsOneWidget);
      expect(find.text('DRIVER'), findsOneWidget);

      // The profile screen is a ListView; the sign-out button sits below the
      // fold at test viewport height.
      final signOutButton = find.widgetWithText(OutlinedButton, 'Sign out');
      await tester.scrollUntilVisible(signOutButton, 200, scrollable: find.byType(Scrollable).first);
      await tester.pumpAndSettle();

      await tester.tap(signOutButton);
      await tester.pumpAndSettle();
      await tester.tap(find.widgetWithText(TextButton, 'Sign out'));
      await tester.pumpAndSettle();

      expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
    });
  });

  group('unimplemented tabs', () {
    testWidgets('say so instead of showing placeholder data', (tester) async {
      await tester.pumpWidget(
        _boot(
          routes: {'/auth/me': (200, _user()), '/health': (200, _healthBody)},
          storedSession: _session(),
        ),
      );
      await tester.pumpAndSettle();

      await tester.tap(find.text('Trip'));
      await tester.pumpAndSettle();

      expect(find.text('NOT IMPLEMENTED YET'), findsOneWidget);
      expect(find.text('PHASE 14'), findsOneWidget);
    });
  });

  group('risk contract', () {
    test('band boundaries map to the documented levels', () {
      expect(riskLevelFromScore(0), RiskLevel.low);
      expect(riskLevelFromScore(25), RiskLevel.low);
      expect(riskLevelFromScore(26), RiskLevel.moderate);
      expect(riskLevelFromScore(50), RiskLevel.moderate);
      expect(riskLevelFromScore(51), RiskLevel.high);
      expect(riskLevelFromScore(75), RiskLevel.high);
      expect(riskLevelFromScore(76), RiskLevel.critical);
      expect(riskLevelFromScore(100), RiskLevel.critical);
    });

    test('scores outside 0-100 are clamped', () {
      expect(riskLevelFromScore(-10), RiskLevel.low);
      expect(riskLevelFromScore(500), RiskLevel.critical);
    });

    test('every risk level has a distinct palette and a text label', () {
      final colours = <Color>{};
      for (final level in RiskLevel.values) {
        final palette = riskPaletteFor(level);
        expect(palette.label, isNotEmpty);
        colours.add(palette.foreground);
      }
      expect(colours.length, RiskLevel.values.length);
    });

    test('wire values round-trip through tryParse', () {
      expect(Role.tryParse('TRAFFIC_OPERATOR'), Role.trafficOperator);
      expect(EventType.tryParse('HELMET_VIOLATION'), EventType.helmetViolation);
      expect(Determination.tryParse('UNABLE_TO_DETERMINE'), Determination.unableToDetermine);
      expect(Role.tryParse('NOT_A_ROLE'), isNull);
      expect(Role.tryParse(null), isNull);
    });
  });

  group('auth models', () {
    test('an unknown role never fails open to something privileged', () {
      final user = AuthUser.fromJson({'id': 'x', 'email': 'a@b.local', 'role': 'SUPERUSER'});
      expect(user.role, Role.driver);
    });

    test('only drivers and admins may use the driver app', () {
      for (final role in Role.values) {
        final user = AuthUser.fromJson({'id': 'x', 'email': 'a@b.local', 'role': role.wire});
        expect(user.canUseDriverApp, role == Role.driver || role == Role.admin);
      }
    });

    test('an expired session is detected', () {
      final expired = AuthSession(
        token: 't',
        user: AuthUser.fromJson(_user()),
        expiresAt: DateTime.now().subtract(const Duration(minutes: 1)),
      );
      expect(expired.isExpired, isTrue);
    });

    test('a session round-trips through JSON', () {
      final original = _session();
      final restored = AuthSession.fromJson(jsonDecode(jsonEncode(original.toJson())));
      expect(restored.token, original.token);
      expect(restored.user.role, original.user.role);
      expect(restored.isExpired, isFalse);
    });
  });
}
