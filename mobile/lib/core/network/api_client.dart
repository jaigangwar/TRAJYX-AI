import 'dart:convert';
import 'dart:io';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';

/// A failure reported by the TRAJYX API, decoded from the shared error
/// envelope `{"error": {"code", "message", "request_id"}}`.
class ApiException implements Exception {
  ApiException({
    required this.statusCode,
    required this.code,
    required this.message,
    this.requestId,
  });

  final int statusCode;
  final String code;
  final String message;
  final String? requestId;

  /// True when the API could not be reached at all, as opposed to reporting
  /// a failure. The driver app treats these differently: offline is expected
  /// on the road, a server error is not.
  bool get isOffline => statusCode == 0;

  bool get isAuthFailure => statusCode == 401;

  @override
  String toString() => 'ApiException($statusCode $code): $message';
}

/// Supplies the current bearer token, or null when signed out.
typedef TokenProvider = Future<String?> Function();

/// Thin JSON client for the TRAJYX API.
///
/// Deliberately small: no caching, no retry policy, no model knowledge. The
/// feature layer owns those decisions, which keeps this testable with a stub
/// [http.Client].
class ApiClient {
  ApiClient({http.Client? httpClient, TokenProvider? tokenProvider, String? baseUrl})
      : _http = httpClient ?? http.Client(),
        _tokenProvider = tokenProvider,
        _root = baseUrl ?? AppConfig.apiRoot;

  final http.Client _http;
  final TokenProvider? _tokenProvider;
  final String _root;

  static const Duration _timeout = Duration(seconds: 20);

  Future<Map<String, dynamic>> getJson(
    String path, {
    Map<String, String>? query,
    bool anonymous = false,
  }) async {
    final response = await _send('GET', path, query: query, anonymous: anonymous);
    return _decodeObject(response);
  }

  Future<List<dynamic>> getJsonList(
    String path, {
    Map<String, String>? query,
    bool anonymous = false,
  }) async {
    final response = await _send('GET', path, query: query, anonymous: anonymous);
    final decoded = _decode(response);
    if (decoded is List) return decoded;
    throw ApiException(
      statusCode: response.statusCode,
      code: 'CONTRACT_MISMATCH',
      message: 'Expected a JSON array from $path.',
    );
  }

  Future<Map<String, dynamic>> postJson(
    String path, {
    Object? body,
    Map<String, String>? query,
    bool anonymous = false,
  }) async {
    final response = await _send('POST', path, body: body, query: query, anonymous: anonymous);
    return _decodeObject(response);
  }

  Future<http.Response> _send(
    String method,
    String path, {
    Object? body,
    Map<String, String>? query,
    bool anonymous = false,
  }) async {
    final uri = Uri.parse('$_root${path.startsWith('/') ? path : '/$path'}')
        .replace(queryParameters: query?.isEmpty ?? true ? null : query);

    final headers = <String, String>{'Accept': 'application/json'};
    if (body != null) headers['Content-Type'] = 'application/json';

    if (!anonymous && _tokenProvider != null) {
      final token = await _tokenProvider();
      if (token != null) headers['Authorization'] = 'Bearer $token';
    }

    final request = http.Request(method, uri)..headers.addAll(headers);
    if (body != null) request.body = jsonEncode(body);

    try {
      final streamed = await _http.send(request).timeout(_timeout);
      return await http.Response.fromStream(streamed);
    } on SocketException {
      throw ApiException(
        statusCode: 0,
        code: 'OFFLINE',
        message: 'No connection to TRAJYX. Cached risk zones are still in use.',
      );
    } on HttpException catch (error) {
      throw ApiException(statusCode: 0, code: 'NETWORK_ERROR', message: error.message);
    }
  }

  Object? _decode(http.Response response) {
    final Object? decoded = response.body.isEmpty ? null : jsonDecode(response.body);

    if (response.statusCode >= 400) {
      final envelope = decoded is Map<String, dynamic> ? decoded['error'] : null;
      if (envelope is Map<String, dynamic>) {
        throw ApiException(
          statusCode: response.statusCode,
          code: envelope['code'] as String? ?? 'HTTP_ERROR',
          message: envelope['message'] as String? ?? 'Request failed.',
          requestId: envelope['request_id'] as String?,
        );
      }
      throw ApiException(
        statusCode: response.statusCode,
        code: 'HTTP_ERROR',
        message: response.reasonPhrase ?? 'Request failed.',
      );
    }
    return decoded;
  }

  Map<String, dynamic> _decodeObject(http.Response response) {
    final decoded = _decode(response);
    if (decoded is Map<String, dynamic>) return decoded;
    throw ApiException(
      statusCode: response.statusCode,
      code: 'CONTRACT_MISMATCH',
      message: 'Expected a JSON object in the response body.',
    );
  }

  void close() => _http.close();
}
