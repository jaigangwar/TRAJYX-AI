import 'package:flutter/material.dart';

import '../contracts/domain.dart';

/// TRAJYX colour and spacing tokens.
///
/// These mirror `web/src/styles/tokens.css` so the driver app and the operator
/// dashboard are recognisably one product. The values are duplicated rather
/// than generated because Flutter needs compile-time constants; the two files
/// are small and change together, and a test asserts the risk ramp matches the
/// shared contract's band count.
///
/// The driver app is dark-only by design: it is used behind a windscreen, often
/// at night, and a light theme would be a glare hazard.
abstract final class TrajyxColors {
  // Surfaces
  static const ground = Color(0xFF0D1114);
  static const surface = Color(0xFF14191D);
  static const surfaceRaised = Color(0xFF1A2126);
  static const surfaceSunken = Color(0xFF0A0E11);

  // Lines
  static const line = Color(0xFF232C33);
  static const lineStrong = Color(0xFF313C45);

  // Ink
  static const ink = Color(0xFFE8EDF1);
  static const inkMuted = Color(0xFF9AA7B2);
  static const inkSubtle = Color(0xFF6B7884);
  static const inkInverse = Color(0xFF0D1114);

  // Brand
  static const accent = Color(0xFF14B8A1);
  static const accentDim = Color(0xFF0D3B36);
  static const accentLine = Color(0xFF1A5E56);

  // Safety ramp. Reserved for risk semantics — never decoration.
  static const riskLow = Color(0xFF3FB950);
  static const riskLowDim = Color(0xFF10291A);
  static const riskModerate = Color(0xFFD9A520);
  static const riskModerateDim = Color(0xFF2E2510);
  static const riskHigh = Color(0xFFE8833A);
  static const riskHighDim = Color(0xFF331F11);
  static const riskCritical = Color(0xFFE5484D);
  static const riskCriticalDim = Color(0xFF3A1417);

  static const info = Color(0xFF3B82F6);
  static const infoDim = Color(0xFF10243F);
  static const offline = Color(0xFF6B7884);
}

/// Colour pair for a risk level: a saturated foreground and a tinted fill.
class RiskPalette {
  const RiskPalette({required this.label, required this.foreground, required this.background});

  final String label;
  final Color foreground;
  final Color background;
}

/// The single mapping from risk level to colour used across the driver app.
const Map<RiskLevel, RiskPalette> kRiskPalette = {
  RiskLevel.low: RiskPalette(
    label: 'Low',
    foreground: TrajyxColors.riskLow,
    background: TrajyxColors.riskLowDim,
  ),
  RiskLevel.moderate: RiskPalette(
    label: 'Moderate',
    foreground: TrajyxColors.riskModerate,
    background: TrajyxColors.riskModerateDim,
  ),
  RiskLevel.high: RiskPalette(
    label: 'High',
    foreground: TrajyxColors.riskHigh,
    background: TrajyxColors.riskHighDim,
  ),
  RiskLevel.critical: RiskPalette(
    label: 'Critical',
    foreground: TrajyxColors.riskCritical,
    background: TrajyxColors.riskCriticalDim,
  ),
};

RiskPalette riskPaletteFor(RiskLevel level) => kRiskPalette[level]!;

RiskPalette riskPaletteForScore(num score) => riskPaletteFor(riskLevelFromScore(score));

/// 4px spacing scale. The driver app is read at a glance, so it is less dense
/// than the dashboard: touch targets stay at or above 48px.
abstract final class Space {
  static const double xs = 4;
  static const double sm = 8;
  static const double md = 12;
  static const double lg = 16;
  static const double xl = 24;
  static const double xxl = 32;
}

abstract final class Radii {
  static const double sm = 4;
  static const double md = 6;
  static const double lg = 10;
}
