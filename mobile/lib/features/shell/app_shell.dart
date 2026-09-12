import 'package:flutter/material.dart';

import '../../core/theme/tokens.dart';
import '../../widgets/state_views.dart';
import '../home/home_screen.dart';

/// Bottom-navigation shell.
///
/// Six destinations as specified for the driver experience. Tabs whose screens
/// are not implemented yet render [_PendingScreen], which names the delivering
/// phase instead of showing placeholder data.
class AppShell extends StatefulWidget {
  const AppShell({super.key});

  @override
  State<AppShell> createState() => _AppShellState();
}

class _AppShellState extends State<AppShell> {
  int _index = 0;

  static const _destinations = <_Destination>[
    _Destination('Home', Icons.shield_outlined, Icons.shield),
    _Destination('Trip', Icons.navigation_outlined, Icons.navigation),
    _Destination('Alerts', Icons.warning_amber_outlined, Icons.warning_amber_rounded),
    _Destination('Safety', Icons.speed_outlined, Icons.speed),
    _Destination('History', Icons.history_outlined, Icons.history),
    _Destination('Profile', Icons.person_outline, Icons.person),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(child: _screenFor(_index)),
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (next) => setState(() => _index = next),
        destinations: [
          for (final destination in _destinations)
            NavigationDestination(
              icon: Icon(destination.icon),
              selectedIcon: Icon(destination.selectedIcon),
              label: destination.label,
            ),
        ],
      ),
    );
  }

  Widget _screenFor(int index) {
    switch (index) {
      case 0:
        return const HomeScreen();
      case 1:
        return const _PendingScreen(
          title: 'Trip',
          phase: 14,
          description:
              'Start a trip and TRAJYX follows your position and heading, matches you to a road '
              'segment, and warns you before you reach a high-risk zone ahead on your route.',
        );
      case 2:
        return const _PendingScreen(
          title: 'Alerts',
          phase: 14,
          description:
              'Warnings raised during your trips, with the risk score and the factors behind each '
              'one. Alerts are de-duplicated and rate-limited so the app never nags.',
        );
      case 3:
        return const _PendingScreen(
          title: 'Safety',
          phase: 13,
          description:
              'Your driving safety summary, built from measured trip behaviour rather than a '
              'generic score.',
        );
      case 4:
        return const _PendingScreen(
          title: 'History',
          phase: 13,
          description: 'Past trips with the route travelled, alerts received and hazards reported.',
        );
      default:
        return const _PendingScreen(
          title: 'Profile',
          phase: 1,
          description: 'Account, sign-out, alert thresholds and voice-warning preferences.',
        );
    }
  }
}

class _Destination {
  const _Destination(this.label, this.icon, this.selectedIcon);

  final String label;
  final IconData icon;
  final IconData selectedIcon;
}

class _PendingScreen extends StatelessWidget {
  const _PendingScreen({required this.title, required this.phase, required this.description});

  final String title;
  final int phase;
  final String description;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(Space.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                title,
                style: const TextStyle(
                  color: TrajyxColors.ink,
                  fontSize: 20,
                  fontWeight: FontWeight.w600,
                ),
              ),
              const Spacer(),
              TrajyxChip(label: 'Phase $phase'),
            ],
          ),
          const SizedBox(height: Space.lg),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(Space.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const SectionLabel('Not implemented yet'),
                  const SizedBox(height: Space.sm),
                  Text(
                    description,
                    style: const TextStyle(
                      color: TrajyxColors.inkMuted,
                      fontSize: 13.5,
                      height: 1.5,
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
