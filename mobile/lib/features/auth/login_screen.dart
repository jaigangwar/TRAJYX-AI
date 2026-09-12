import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/network/api_client.dart';
import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../../widgets/state_views.dart';
import '../../widgets/trajyx_mark.dart';
import 'auth_controller.dart';
import 'auth_models.dart';

/// Sign-in and driver registration.
///
/// One screen with two modes rather than two screens: a driver installing the
/// app either has an account or needs one, and making them navigate to find
/// out is friction for no benefit.
class LoginScreen extends ConsumerStatefulWidget {
  const LoginScreen({super.key});

  @override
  ConsumerState<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends ConsumerState<LoginScreen> {
  final _formKey = GlobalKey<FormState>();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _nameController = TextEditingController();

  bool _registering = false;
  bool _busy = false;
  bool _obscurePassword = true;
  String? _error;

  @override
  void dispose() {
    _emailController.dispose();
    _passwordController.dispose();
    _nameController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _busy = true;
      _error = null;
    });

    final controller = ref.read(authControllerProvider.notifier);
    try {
      if (_registering) {
        await controller.register(
          email: _emailController.text,
          password: _passwordController.text,
          displayName: _nameController.text.trim(),
        );
      } else {
        await controller.signIn(
          email: _emailController.text,
          password: _passwordController.text,
        );
      }
      // On success the auth state changes and the app shell replaces this
      // screen, so there is nothing to navigate here.
    } on ApiException catch (error) {
      if (mounted) setState(() => _error = error.message);
    } catch (_) {
      if (mounted) {
        setState(() => _error = 'Something went wrong. Please try again.');
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    // An involuntary sign-out (suspended account, wrong role) explains itself.
    final authState = ref.watch(authControllerProvider);
    final involuntaryMessage = authState is AuthSignedOut ? authState.message : null;

    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(Space.xl),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Form(
                key: _formKey,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const SizedBox(height: Space.xl),
                    const Center(child: TrajyxMark(size: 60)),
                    const SizedBox(height: Space.lg),
                    const Center(
                      child: Text(
                        'TRAJYX',
                        style: TextStyle(
                          color: TrajyxColors.ink,
                          fontSize: 24,
                          fontWeight: FontWeight.w700,
                          letterSpacing: 4,
                        ),
                      ),
                    ),
                    const SizedBox(height: Space.xs),
                    Center(
                      child: Text(
                        'SAFER ROADS, BRIGHTER TOMORROWS',
                        style: TextStyle(
                          color: TrajyxColors.inkSubtle,
                          fontSize: 9.5,
                          fontWeight: FontWeight.w600,
                          letterSpacing: 1.4,
                        ),
                      ),
                    ),
                    const SizedBox(height: Space.xxl),

                    if (involuntaryMessage != null && _error == null)
                      _Notice(message: involuntaryMessage, tone: _NoticeTone.warning),
                    if (_error != null) _Notice(message: _error!, tone: _NoticeTone.error),

                    TextFormField(
                      controller: _emailController,
                      keyboardType: TextInputType.emailAddress,
                      textInputAction: TextInputAction.next,
                      autofillHints: const [AutofillHints.email],
                      enabled: !_busy,
                      decoration: const InputDecoration(labelText: 'Email address'),
                      validator: (value) {
                        final text = value?.trim() ?? '';
                        if (text.isEmpty) return 'Enter your email address';
                        // Deliberately loose: the API is the authority on what
                        // a valid address is, and a strict client regex would
                        // reject internal domains the backend accepts.
                        if (!text.contains('@') || text.endsWith('@')) {
                          return 'Enter a valid email address';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: Space.md),

                    if (_registering) ...[
                      TextFormField(
                        controller: _nameController,
                        textInputAction: TextInputAction.next,
                        enabled: !_busy,
                        decoration: const InputDecoration(
                          labelText: 'Name (optional)',
                        ),
                      ),
                      const SizedBox(height: Space.md),
                    ],

                    TextFormField(
                      controller: _passwordController,
                      obscureText: _obscurePassword,
                      textInputAction: TextInputAction.done,
                      autofillHints: const [AutofillHints.password],
                      enabled: !_busy,
                      onFieldSubmitted: (_) => _submit(),
                      decoration: InputDecoration(
                        labelText: 'Password',
                        suffixIcon: IconButton(
                          icon: Icon(
                            _obscurePassword ? Icons.visibility_outlined : Icons.visibility_off_outlined,
                            size: 20,
                            color: TrajyxColors.inkSubtle,
                          ),
                          tooltip: _obscurePassword ? 'Show password' : 'Hide password',
                          onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                        ),
                      ),
                      validator: (value) {
                        final text = value ?? '';
                        if (text.isEmpty) return 'Enter your password';
                        // Only enforced when setting a password; the backend
                        // owns the full rule and reports it.
                        if (_registering && text.length < 10) {
                          return 'Use at least 10 characters';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: Space.xl),

                    FilledButton(
                      onPressed: _busy ? null : _submit,
                      child: _busy
                          ? const SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2.2,
                                color: TrajyxColors.inkInverse,
                              ),
                            )
                          : Text(_registering ? 'Create account' : 'Sign in'),
                    ),
                    const SizedBox(height: Space.md),

                    TextButton(
                      onPressed: _busy
                          ? null
                          : () => setState(() {
                                _registering = !_registering;
                                _error = null;
                              }),
                      child: Text(
                        _registering
                            ? 'I already have an account'
                            : 'Create a driver account',
                        style: const TextStyle(color: TrajyxColors.accent, fontSize: 13.5),
                      ),
                    ),

                    const SizedBox(height: Space.xl),
                    const _DeploymentNotice(),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

enum _NoticeTone { warning, error }

class _Notice extends StatelessWidget {
  const _Notice({required this.message, required this.tone});

  final String message;
  final _NoticeTone tone;

  @override
  Widget build(BuildContext context) {
    final isError = tone == _NoticeTone.error;
    return Container(
      margin: const EdgeInsets.only(bottom: Space.lg),
      padding: const EdgeInsets.all(Space.md),
      decoration: BoxDecoration(
        color: isError ? TrajyxColors.riskCriticalDim : TrajyxColors.riskModerateDim,
        border: Border.all(
          color: isError ? TrajyxColors.riskCritical : TrajyxColors.riskModerate,
        ),
        borderRadius: BorderRadius.circular(Radii.sm),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            isError ? Icons.error_outline : Icons.info_outline,
            size: 18,
            color: isError ? TrajyxColors.riskCritical : TrajyxColors.riskModerate,
          ),
          const SizedBox(width: Space.sm),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                color: isError ? TrajyxColors.riskCritical : TrajyxColors.riskModerate,
                fontSize: 13,
                height: 1.4,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// States which backend the deployment is using, so a demo build is never
/// mistaken for a production one.
class _DeploymentNotice extends ConsumerWidget {
  const _DeploymentNotice();

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(platformStatusProvider);

    return status.when(
      loading: () => const SizedBox(height: 24),
      error: (_, _) => Text(
        'Cannot reach the TRAJYX API. Check your connection and the configured server address.',
        textAlign: TextAlign.center,
        style: const TextStyle(color: TrajyxColors.inkSubtle, fontSize: 12),
      ),
      data: (data) => Wrap(
        alignment: WrapAlignment.center,
        spacing: Space.sm,
        runSpacing: Space.sm,
        children: [
          if (data.demoMode) const TrajyxChip.demo(),
          TrajyxChip(label: '${data.authBackend} auth'),
          if (data.environment != 'production') TrajyxChip(label: data.environment),
        ],
      ),
    );
  }
}
