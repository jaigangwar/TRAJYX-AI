import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'network/api_client.dart';

/// Shared API client. Feature providers depend on this rather than
/// constructing their own, so tests can override it in one place.
final apiClientProvider = Provider<ApiClient>((ref) {
  final client = ApiClient();
  ref.onDispose(client.close);
  return client;
});

/// Backend capability report, used to label degraded and demo modes honestly.
class PlatformStatus {
  const PlatformStatus({
    required this.service,
    required this.version,
    required this.environment,
    required this.contractVersion,
    required this.dataBackend,
    required this.authBackend,
    required this.demoMode,
  });

  factory PlatformStatus.fromJson(Map<String, dynamic> json) {
    final capabilities = json['capabilities'] as Map<String, dynamic>? ?? const {};
    return PlatformStatus(
      service: json['service'] as String? ?? 'TRAJYX API',
      version: json['version'] as String? ?? 'unknown',
      environment: json['environment'] as String? ?? 'unknown',
      contractVersion: json['contract_version'] as String? ?? 'unknown',
      dataBackend: capabilities['data_backend'] as String? ?? 'unknown',
      authBackend: capabilities['auth_backend'] as String? ?? 'unknown',
      demoMode: capabilities['demo_mode'] as bool? ?? false,
    );
  }

  final String service;
  final String version;
  final String environment;
  final String contractVersion;
  final String dataBackend;
  final String authBackend;
  final bool demoMode;
}

/// Reaches the API's health endpoint. Proves real connectivity from the device
/// rather than assuming it.
final platformStatusProvider = FutureProvider<PlatformStatus>((ref) async {
  final client = ref.watch(apiClientProvider);
  final json = await client.getJson('/health', anonymous: true);
  return PlatformStatus.fromJson(json);
});
