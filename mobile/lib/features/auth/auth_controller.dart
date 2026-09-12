import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/providers.dart';
import 'auth_models.dart';
import 'auth_repository.dart';

/// Session state machine.
class AuthController extends Notifier<AuthState> {
  @override
  AuthState build() {
    // Restoration is kicked off immediately; the UI shows a splash until it
    // resolves rather than flashing the login screen at a signed-in user.
    Future.microtask(restore);
    return const AuthRestoring();
  }

  AuthRepository get _repository => ref.read(authRepositoryProvider);

  /// Read the stored session and confirm it with the API.
  Future<void> restore() async {
    final stored = await _repository.readStoredSession();
    if (stored == null) {
      state = const AuthSignedOut();
      return;
    }

    // Publish the token first so the verification request can use it.
    ref.read(authTokenProvider.notifier).set(stored.token);

    try {
      final user = await _repository.fetchProfile();
      if (!user.isActive) {
        await _signOutLocally(message: 'This account is suspended. Contact an administrator.');
        return;
      }
      if (!user.canUseDriverApp) {
        await _signOutLocally(
          message:
            'This account has the ${user.role.wire} role. The driver app is for driver accounts; '
            'use the TRAJYX web console instead.',
        );
        return;
      }
      // Trust the server's profile over the stored copy.
      state = AuthSignedIn(AuthSession(
        token: stored.token,
        user: user,
        expiresAt: stored.expiresAt,
      ));
    } on ApiException catch (error) {
      if (error.isOffline) {
        // Offline on launch is normal on the road. The stored session stays
        // valid until its own deadline, so the driver keeps cached risk zones
        // and alerting rather than being locked out by a dead connection.
        state = AuthSignedIn(stored);
        return;
      }
      await _signOutLocally(
        message: error.isAuthFailure ? null : error.message,
      );
    }
  }

  /// Sign in with email and password.
  ///
  /// Rethrows [ApiException] so the form can render the API's own message.
  Future<void> signIn({required String email, required String password}) async {
    final session = await _repository.signIn(email: email, password: password);

    if (!session.user.canUseDriverApp) {
      // Valid credentials, wrong app. Do not persist the session.
      throw ApiException(
        statusCode: 403,
        code: 'WRONG_APP',
        message:
          'This account has the ${session.user.role.wire} role. The driver app is for driver '
          'accounts; use the TRAJYX web console instead.',
      );
    }

    await _repository.saveSession(session);
    ref.read(authTokenProvider.notifier).set(session.token);
    state = AuthSignedIn(session);
  }

  Future<void> register({
    required String email,
    required String password,
    String? displayName,
  }) async {
    await _repository.registerDriver(
      email: email,
      password: password,
      displayName: displayName,
    );
    // Registration does not return a token, so sign in with the same details.
    await signIn(email: email, password: password);
  }

  Future<void> signOut() async {
    await _repository.signOut();
    ref.read(authTokenProvider.notifier).set(null);
    state = const AuthSignedOut();
  }

  Future<void> _signOutLocally({String? message}) async {
    await _repository.clearSession();
    ref.read(authTokenProvider.notifier).set(null);
    state = AuthSignedOut(message: message);
  }
}

final authControllerProvider = NotifierProvider<AuthController, AuthState>(AuthController.new);

final authRepositoryProvider = Provider<AuthRepository>((ref) {
  return AuthRepository(client: ref.watch(apiClientProvider));
});

/// Convenience selector for the signed-in user, or null.
final currentUserProvider = Provider<AuthUser?>((ref) {
  final state = ref.watch(authControllerProvider);
  return state is AuthSignedIn ? state.user : null;
});
