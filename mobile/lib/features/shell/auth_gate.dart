import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/tokens.dart';
import '../../widgets/trajyx_mark.dart';
import '../auth/auth_controller.dart';
import '../auth/auth_models.dart';
import '../auth/login_screen.dart';
import 'app_shell.dart';

/// Chooses between the splash, the login screen and the app.
///
/// The splash exists so a returning driver does not see the login form flash
/// before their stored session is confirmed — on a phone that flicker reads as
/// "I have been signed out".
class AuthGate extends ConsumerWidget {
  const AuthGate({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(authControllerProvider);

    return switch (state) {
      AuthRestoring() => const _Splash(),
      AuthSignedOut() => const LoginScreen(),
      AuthSignedIn() => const AppShell(),
    };
  }
}

class _Splash extends StatelessWidget {
  const _Splash();

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            TrajyxMark(size: 64),
            SizedBox(height: Space.xl),
            Text(
              'TRAJYX',
              style: TextStyle(
                color: TrajyxColors.ink,
                fontSize: 20,
                fontWeight: FontWeight.w700,
                letterSpacing: 3.5,
              ),
            ),
            SizedBox(height: Space.xxl),
            SizedBox(
              width: 22,
              height: 22,
              child: CircularProgressIndicator(strokeWidth: 2.2),
            ),
          ],
        ),
      ),
    );
  }
}
