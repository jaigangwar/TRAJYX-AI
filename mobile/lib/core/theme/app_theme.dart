import 'package:flutter/material.dart';

import 'tokens.dart';

/// Material theme for the driver app.
///
/// Tuned for in-vehicle use: dark ground, high-contrast numerals, generous
/// touch targets, and no decorative elevation. Numbers use tabular figures so
/// a changing speed or distance does not shift the layout.
abstract final class AppTheme {
  static ThemeData dark() {
    const colorScheme = ColorScheme.dark(
      primary: TrajyxColors.accent,
      onPrimary: TrajyxColors.inkInverse,
      secondary: TrajyxColors.accent,
      onSecondary: TrajyxColors.inkInverse,
      surface: TrajyxColors.surface,
      onSurface: TrajyxColors.ink,
      error: TrajyxColors.riskCritical,
      onError: TrajyxColors.ink,
      outline: TrajyxColors.lineStrong,
      outlineVariant: TrajyxColors.line,
    );

    final base = ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: TrajyxColors.ground,
      canvasColor: TrajyxColors.ground,
      splashFactory: InkSparkle.splashFactory,
    );

    return base.copyWith(
      textTheme: _textTheme(base.textTheme),
      appBarTheme: const AppBarTheme(
        backgroundColor: TrajyxColors.surface,
        foregroundColor: TrajyxColors.ink,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
        titleTextStyle: TextStyle(
          color: TrajyxColors.ink,
          fontSize: 16,
          fontWeight: FontWeight.w600,
          letterSpacing: 0.2,
        ),
        shape: Border(bottom: BorderSide(color: TrajyxColors.line)),
      ),
      cardTheme: CardThemeData(
        color: TrajyxColors.surface,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(Radii.md),
          side: const BorderSide(color: TrajyxColors.line),
        ),
      ),
      dividerTheme: const DividerThemeData(
        color: TrajyxColors.line,
        thickness: 1,
        space: 1,
      ),
      navigationBarTheme: NavigationBarThemeData(
        backgroundColor: TrajyxColors.surface,
        indicatorColor: TrajyxColors.accentDim,
        elevation: 0,
        height: 62,
        labelBehavior: NavigationDestinationLabelBehavior.alwaysShow,
        iconTheme: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return IconThemeData(
            size: 22,
            color: selected ? TrajyxColors.accent : TrajyxColors.inkSubtle,
          );
        }),
        labelTextStyle: WidgetStateProperty.resolveWith((states) {
          final selected = states.contains(WidgetState.selected);
          return TextStyle(
            fontSize: 11,
            fontWeight: selected ? FontWeight.w600 : FontWeight.w500,
            color: selected ? TrajyxColors.accent : TrajyxColors.inkSubtle,
          );
        }),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: TrajyxColors.accent,
          foregroundColor: TrajyxColors.inkInverse,
          // 52px: comfortably tappable in a moving vehicle.
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md)),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: TrajyxColors.ink,
          side: const BorderSide(color: TrajyxColors.lineStrong),
          minimumSize: const Size.fromHeight(52),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.md)),
          textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: TrajyxColors.surfaceSunken,
        contentPadding: const EdgeInsets.symmetric(horizontal: Space.md, vertical: Space.md),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(Radii.sm),
          borderSide: const BorderSide(color: TrajyxColors.line),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(Radii.sm),
          borderSide: const BorderSide(color: TrajyxColors.line),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(Radii.sm),
          borderSide: const BorderSide(color: TrajyxColors.accent, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(Radii.sm),
          borderSide: const BorderSide(color: TrajyxColors.riskCritical),
        ),
        labelStyle: const TextStyle(color: TrajyxColors.inkMuted, fontSize: 14),
        hintStyle: const TextStyle(color: TrajyxColors.inkSubtle, fontSize: 14),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: TrajyxColors.surfaceRaised,
        contentTextStyle: const TextStyle(color: TrajyxColors.ink, fontSize: 14),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(Radii.sm)),
        behavior: SnackBarBehavior.floating,
      ),
      progressIndicatorTheme: const ProgressIndicatorThemeData(
        color: TrajyxColors.accent,
        linearTrackColor: TrajyxColors.line,
        circularTrackColor: TrajyxColors.line,
      ),
    );
  }

  static TextTheme _textTheme(TextTheme base) {
    // `FontFeature.tabularFigures` keeps changing numerals from shifting the
    // layout, which matters for live speed and distance readouts.
    const tabular = [FontFeature.tabularFigures()];

    return base.copyWith(
      displayLarge: base.displayLarge?.copyWith(
        color: TrajyxColors.ink,
        fontWeight: FontWeight.w700,
        fontFeatures: tabular,
        letterSpacing: -1,
      ),
      headlineMedium: base.headlineMedium?.copyWith(
        color: TrajyxColors.ink,
        fontWeight: FontWeight.w600,
        fontFeatures: tabular,
      ),
      titleLarge: base.titleLarge?.copyWith(color: TrajyxColors.ink, fontWeight: FontWeight.w600),
      titleMedium: base.titleMedium?.copyWith(color: TrajyxColors.ink, fontWeight: FontWeight.w600),
      bodyLarge: base.bodyLarge?.copyWith(color: TrajyxColors.ink),
      bodyMedium: base.bodyMedium?.copyWith(color: TrajyxColors.inkMuted),
      bodySmall: base.bodySmall?.copyWith(color: TrajyxColors.inkSubtle),
      labelLarge: base.labelLarge?.copyWith(color: TrajyxColors.ink, fontWeight: FontWeight.w600),
      labelSmall: base.labelSmall?.copyWith(
        color: TrajyxColors.inkSubtle,
        fontWeight: FontWeight.w600,
        letterSpacing: 0.8,
      ),
    );
  }
}
