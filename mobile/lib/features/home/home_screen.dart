import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../core/theme/tokens.dart';
import '../../widgets/state_views.dart';
import '../../widgets/trajyx_mark.dart';

/// Phase 0 home screen.
///
/// Its job right now is to prove the device genuinely reaches the TRAJYX API
/// and to report the platform's real state. The driver-facing safety score,
/// nearby-risk readout and alert card arrive in phases 13 and 14, once there
/// are risk zones and a GPS engine behind them — they are deliberately absent
/// rather than mocked, because a safety score the app has not computed would be
/// the single most misleading thing it could show.
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(platformStatusProvider);

    return RefreshIndicator(
      onRefresh: () => ref.refresh(platformStatusProvider.future),
      child: ListView(
        padding: const EdgeInsets.all(Space.lg),
        children: [
          const _Header(),
          const SizedBox(height: Space.xl),
          status.when(
            loading: () => const SizedBox(
              height: 180,
              child: LoadingView(label: 'Reaching TRAJYX'),
            ),
            error: (error, _) => SizedBox(
              height: 260,
              child: ErrorView(
                error: error,
                title: 'Cannot reach TRAJYX',
                onRetry: () => ref.invalidate(platformStatusProvider),
              ),
            ),
            data: (data) => _PlatformCard(status: data),
          ),
          const SizedBox(height: Space.md),
          const _UpcomingCard(),
        ],
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header();

  @override
  Widget build(BuildContext context) {
    return const Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        TrajyxWordmark(markSize: 34, showDescriptor: true),
        SizedBox(height: Space.md),
        Text(
          'Safer roads, brighter tomorrows.',
          style: TextStyle(color: TrajyxColors.inkMuted, fontSize: 13.5),
        ),
      ],
    );
  }
}

class _PlatformCard extends StatelessWidget {
  const _PlatformCard({required this.status});

  final PlatformStatus status;

  @override
  Widget build(BuildContext context) {
    final localAuth = status.authBackend == 'local';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Space.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const SectionLabel('Connected'),
                const Spacer(),
                if (status.demoMode) const TrajyxChip.demo(),
              ],
            ),
            const SizedBox(height: Space.md),
            Row(
              children: [
                Container(
                  width: 8,
                  height: 8,
                  decoration: const BoxDecoration(
                    color: TrajyxColors.riskLow,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: Space.sm),
                Text(
                  status.service,
                  style: const TextStyle(
                    color: TrajyxColors.ink,
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
            const SizedBox(height: Space.lg),
            const Divider(),
            const SizedBox(height: Space.md),
            _Row(label: 'API version', value: status.version),
            _Row(label: 'Contract', value: status.contractVersion),
            _Row(label: 'Environment', value: status.environment),
            _Row(
              label: 'Data source',
              value: status.dataBackend,
              tone: status.dataBackend == 'local' ? TrajyxColors.riskModerate : null,
            ),
            _Row(
              label: 'Sign-in',
              value: localAuth ? 'local (development)' : status.authBackend,
              tone: localAuth ? TrajyxColors.riskModerate : null,
            ),
          ],
        ),
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.label, required this.value, this.tone});

  final String label;
  final String value;
  final Color? tone;

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
          Text(
            value,
            style: TextStyle(
              color: tone ?? TrajyxColors.ink,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _UpcomingCard extends StatelessWidget {
  const _UpcomingCard();

  static const _items = <(String, String)>[
    ('Sign in and driver profile', 'Phase 1'),
    ('Safety score and nearby risk', 'Phase 13'),
    ('Trip tracking with GPS', 'Phase 14'),
    ('Risk-zone alerts with voice', 'Phase 14'),
    ('Hazard reporting', 'Phase 15'),
  ];

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(Space.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const SectionLabel('Not built yet'),
            const SizedBox(height: Space.sm),
            const Text(
              'These screens are stubs in this build. TRAJYX does not show a '
              'safety score or a risk alert until it has actually computed one.',
              style: TextStyle(color: TrajyxColors.inkMuted, fontSize: 12.5, height: 1.45),
            ),
            const SizedBox(height: Space.md),
            for (final (label, phase) in _items)
              Padding(
                padding: const EdgeInsets.only(bottom: Space.sm),
                child: Row(
                  children: [
                    Container(
                      width: 5,
                      height: 5,
                      decoration: BoxDecoration(
                        color: TrajyxColors.inkSubtle,
                        borderRadius: BorderRadius.circular(3),
                      ),
                    ),
                    const SizedBox(width: Space.sm),
                    Expanded(
                      child: Text(
                        label,
                        style: const TextStyle(color: TrajyxColors.inkMuted, fontSize: 13),
                      ),
                    ),
                    Text(
                      phase,
                      style: const TextStyle(color: TrajyxColors.inkSubtle, fontSize: 11.5),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
