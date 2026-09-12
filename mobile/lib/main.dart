import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'core/theme/app_theme.dart';
import 'core/theme/tokens.dart';
import 'features/shell/app_shell.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();

  // The app is dark-only and used behind a windscreen; matching the system
  // chrome to the app ground avoids a bright bar in the driver's eyeline.
  SystemChrome.setSystemUIOverlayStyle(
    const SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: Brightness.light,
      systemNavigationBarColor: TrajyxColors.surface,
      systemNavigationBarIconBrightness: Brightness.light,
    ),
  );

  runApp(const ProviderScope(child: TrajyxApp()));
}

class TrajyxApp extends StatelessWidget {
  const TrajyxApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'TRAJYX',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.dark(),
      // Dark-only by design rather than by omission: a light theme would be a
      // glare hazard for night driving.
      darkTheme: AppTheme.dark(),
      themeMode: ThemeMode.dark,
      home: const AppShell(),
    );
  }
}
