import 'package:flutter/material.dart';

import '../core/network/api_client.dart';
import '../core/theme/tokens.dart';
import 'trajyx_mark.dart';

/// Loading, empty and error views.
///
/// Same contract as the dashboard: a data region is never blank. On a phone
/// used while driving the wording matters more, so errors say what the driver
/// can still rely on (for example, cached risk zones) rather than only what
/// broke.
class LoadingView extends StatelessWidget {
  const LoadingView({super.key, this.label});

  final String? label;

  @override
  Widget build(BuildContext context) => Center(child: TrajyxLoader(label: label));
}

class EmptyView extends StatelessWidget {
  const EmptyView({super.key, required this.message, this.hint, this.icon});

  final String message;
  final String? hint;
  final IconData? icon;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(Space.xl),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (icon != null) ...[
              Icon(icon, size: 30, color: TrajyxColors.inkSubtle),
              const SizedBox(height: Space.md),
            ],
            Text(
              message,
              textAlign: TextAlign.center,
              style: const TextStyle(color: TrajyxColors.inkMuted, fontSize: 14),
            ),
            if (hint != null) ...[
              const SizedBox(height: Space.sm),
              Text(
                hint!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: TrajyxColors.inkSubtle, fontSize: 12.5),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.error, this.onRetry, this.title});

  final Object error;
  final VoidCallback? onRetry;
  final String? title;

  @override
  Widget build(BuildContext context) {
    final api = error is ApiException ? error as ApiException : null;
    final offline = api?.isOffline ?? false;

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(Space.xl),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: Space.sm, vertical: 3),
              decoration: BoxDecoration(
                color: offline ? TrajyxColors.surfaceRaised : TrajyxColors.riskCriticalDim,
                border: Border.all(
                  color: offline ? TrajyxColors.lineStrong : TrajyxColors.riskCritical,
                ),
                borderRadius: BorderRadius.circular(Radii.sm),
              ),
              child: Text(
                offline ? 'OFFLINE' : (api?.code ?? 'ERROR'),
                style: TextStyle(
                  color: offline ? TrajyxColors.inkMuted : TrajyxColors.riskCritical,
                  fontSize: 10.5,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 1,
                ),
              ),
            ),
            const SizedBox(height: Space.md),
            Text(
              title ?? (offline ? 'No connection' : 'Something went wrong'),
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: TrajyxColors.ink,
                fontSize: 15,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: Space.xs),
            Text(
              api?.message ?? error.toString(),
              textAlign: TextAlign.center,
              style: const TextStyle(color: TrajyxColors.inkMuted, fontSize: 13),
            ),
            if (onRetry != null) ...[
              const SizedBox(height: Space.lg),
              SizedBox(
                width: 160,
                child: OutlinedButton(onPressed: onRetry, child: const Text('Retry')),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Section label in the small-caps style shared with the dashboard.
class SectionLabel extends StatelessWidget {
  const SectionLabel(this.text, {super.key});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(
      text.toUpperCase(),
      style: const TextStyle(
        color: TrajyxColors.inkSubtle,
        fontSize: 10.5,
        fontWeight: FontWeight.w700,
        letterSpacing: 1.1,
      ),
    );
  }
}

/// Small chip used for status and provenance labels.
class TrajyxChip extends StatelessWidget {
  const TrajyxChip({
    super.key,
    required this.label,
    this.foreground = TrajyxColors.inkMuted,
    this.background = TrajyxColors.surfaceRaised,
    this.border = TrajyxColors.lineStrong,
  });

  /// Provenance chip for synthetic records. Demo data is always labeled.
  const TrajyxChip.demo({super.key})
      : label = 'DEMO DATA',
        foreground = TrajyxColors.accent,
        background = TrajyxColors.accentDim,
        border = TrajyxColors.accentLine;

  /// Marks a value as derived rather than directly measured.
  const TrajyxChip.estimated({super.key})
      : label = 'ESTIMATED',
        foreground = TrajyxColors.inkMuted,
        background = TrajyxColors.surfaceRaised,
        border = TrajyxColors.lineStrong;

  final String label;
  final Color foreground;
  final Color background;
  final Color border;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
      decoration: BoxDecoration(
        color: background,
        border: Border.all(color: border),
        borderRadius: BorderRadius.circular(Radii.sm),
      ),
      child: Text(
        label.toUpperCase(),
        style: TextStyle(
          color: foreground,
          fontSize: 10,
          fontWeight: FontWeight.w700,
          letterSpacing: 0.7,
        ),
      ),
    );
  }
}
