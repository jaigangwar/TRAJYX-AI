import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../../widgets/state_views.dart';
import '../auth/auth_controller.dart';

/// Account and deployment information, plus sign-out.
///
/// Alert thresholds and voice preferences land in phase 14, when there is an
/// alert engine for them to configure.
class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final user = ref.watch(currentUserProvider);
    final status = ref.watch(platformStatusProvider);

    if (user == null) {
      return const EmptyView(message: 'Not signed in.');
    }

    return ListView(
      padding: const EdgeInsets.all(Space.lg),
      children: [
        Row(
          children: [
            Container(
              width: 46,
              height: 46,
              alignment: Alignment.center,
              decoration: BoxDecoration(
                color: TrajyxColors.accentDim,
                border: Border.all(color: TrajyxColors.accentLine),
                borderRadius: BorderRadius.circular(Radii.md),
              ),
              child: Text(
                _initials(user.label),
                style: const TextStyle(
                  color: TrajyxColors.accent,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            const SizedBox(width: Space.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    user.label,
                    style: const TextStyle(
                      color: TrajyxColors.ink,
                      fontSize: 17,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    user.email,
                    style: const TextStyle(color: TrajyxColors.inkSubtle, fontSize: 13),
                  ),
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: Space.xl),

        Card(
          child: Padding(
            padding: const EdgeInsets.all(Space.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionLabel('Account'),
                const SizedBox(height: Space.md),
                _Row(label: 'Role', value: user.role.wire),
                _Row(label: 'Status', value: user.status),
                _Row(label: 'Account id', value: user.id, monospace: true),
              ],
            ),
          ),
        ),
        const SizedBox(height: Space.md),

        Card(
          child: Padding(
            padding: const EdgeInsets.all(Space.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const SectionLabel('Connected to'),
                    const Spacer(),
                    if (status.value?.demoMode ?? false) const TrajyxChip.demo(),
                  ],
                ),
                const SizedBox(height: Space.md),
                status.when(
                  loading: () => const SizedBox(
                    height: 40,
                    child: Center(
                      child: SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      ),
                    ),
                  ),
                  error: (_, _) => const Text(
                    'Not reachable. Cached data is still in use.',
                    style: TextStyle(color: TrajyxColors.riskModerate, fontSize: 13),
                  ),
                  data: (data) => Column(
                    children: [
                      _Row(label: 'Service', value: data.service),
                      _Row(label: 'API version', value: data.version),
                      _Row(label: 'Environment', value: data.environment),
                      _Row(
                        label: 'Data source',
                        value: data.dataBackend,
                        tone: data.dataBackend == 'local' ? TrajyxColors.riskModerate : null,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: Space.md),

        Card(
          child: Padding(
            padding: const EdgeInsets.all(Space.lg),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SectionLabel('Not built yet'),
                const SizedBox(height: Space.sm),
                const Text(
                  'Alert thresholds, voice-warning preferences and trip history settings arrive '
                  'with the alert engine in phase 14.',
                  style: TextStyle(color: TrajyxColors.inkMuted, fontSize: 12.5, height: 1.45),
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: Space.xl),

        OutlinedButton.icon(
          onPressed: () => _confirmSignOut(context, ref),
          icon: const Icon(Icons.logout, size: 18),
          label: const Text('Sign out'),
        ),
        const SizedBox(height: Space.xl),
      ],
    );
  }

  Future<void> _confirmSignOut(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        backgroundColor: TrajyxColors.surfaceRaised,
        title: const Text('Sign out?'),
        content: const Text(
          'You will stop receiving risk-zone warnings until you sign in again.',
          style: TextStyle(color: TrajyxColors.inkMuted, fontSize: 14),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(dialogContext).pop(true),
            child: const Text('Sign out', style: TextStyle(color: TrajyxColors.riskCritical)),
          ),
        ],
      ),
    );

    if (confirmed ?? false) {
      await ref.read(authControllerProvider.notifier).signOut();
    }
  }

  static String _initials(String label) {
    final trimmed = label.trim();
    if (trimmed.isEmpty) return '?';
    if (trimmed.contains('@')) {
      return trimmed.substring(0, trimmed.length >= 2 ? 2 : 1).toUpperCase();
    }
    final parts = trimmed.split(RegExp(r'\s+')).where((p) => p.isNotEmpty).toList();
    if (parts.length == 1) {
      final single = parts.first;
      return single.substring(0, single.length >= 2 ? 2 : 1).toUpperCase();
    }
    return (parts.first[0] + parts.last[0]).toUpperCase();
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.label, required this.value, this.tone, this.monospace = false});

  final String label;
  final String value;
  final Color? tone;
  final bool monospace;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: Space.sm),
      child: Row(
        children: [
          Expanded(
            child: Text(
              label,
              style: const TextStyle(color: TrajyxColors.inkSubtle, fontSize: 13),
            ),
          ),
          Flexible(
            child: Text(
              value,
              textAlign: TextAlign.right,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: tone ?? TrajyxColors.ink,
                fontSize: monospace ? 11.5 : 13,
                fontWeight: FontWeight.w600,
                fontFamily: monospace ? 'monospace' : null,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
