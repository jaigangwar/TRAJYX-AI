import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:trajyx/core/contracts/domain.dart';
import 'package:trajyx/core/network/api_client.dart';
import 'package:trajyx/core/providers.dart';
import 'package:trajyx/core/theme/tokens.dart';
import 'package:trajyx/main.dart';

/// Health payload matching what `GET /api/v1/health` actually returns.
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

/// Boots the real app with the HTTP layer stubbed, so widget tests exercise
/// the genuine provider graph and decoding path without touching a network.
Widget _bootApp({int statusCode = 200, Map<String, Object?>? body}) {
  final client = MockClient((request) async {
    return http.Response(
      jsonEncode(body ?? _healthBody),
      statusCode,
      headers: {'content-type': 'application/json'},
    );
  });

  return ProviderScope(
    overrides: [
      apiClientProvider.overrideWithValue(
        ApiClient(httpClient: client, baseUrl: 'http://test.local/api/v1'),
      ),
    ],
    child: const TrajyxApp(),
  );
}

void main() {
  testWidgets('app boots into the driver shell with all six destinations', (tester) async {
    await tester.pumpWidget(_bootApp());
    await tester.pumpAndSettle();

    expect(find.text('TRAJYX'), findsOneWidget);
    for (final label in ['Home', 'Trip', 'Alerts', 'Safety', 'History', 'Profile']) {
      expect(find.text(label), findsWidgets, reason: '$label destination is missing');
    }
  });

  testWidgets('home screen renders platform state reported by the API', (tester) async {
    await tester.pumpWidget(_bootApp());
    await tester.pumpAndSettle();

    expect(find.text('TRAJYX API'), findsOneWidget);
    expect(find.text('1.0.0'), findsOneWidget);
    // Demo mode must be visible so synthetic data is never mistaken for real.
    expect(find.text('DEMO DATA'), findsOneWidget);
  });

  testWidgets('home screen shows an actionable error when the API fails', (tester) async {
    await tester.pumpWidget(
      _bootApp(
        statusCode: 503,
        body: {
          'error': {'code': 'DEPENDENCY_UNAVAILABLE', 'message': 'Backing store is unavailable.'},
        },
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Cannot reach TRAJYX'), findsOneWidget);
    expect(find.text('DEPENDENCY_UNAVAILABLE'), findsOneWidget);
    expect(find.widgetWithText(OutlinedButton, 'Retry'), findsOneWidget);
  });

  testWidgets('unimplemented tabs say so instead of showing placeholder data', (tester) async {
    await tester.pumpWidget(_bootApp());
    await tester.pumpAndSettle();

    await tester.tap(find.text('Trip'));
    await tester.pumpAndSettle();

    expect(find.text('NOT IMPLEMENTED YET'), findsOneWidget);
    expect(find.text('PHASE 14'), findsOneWidget);
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
}
