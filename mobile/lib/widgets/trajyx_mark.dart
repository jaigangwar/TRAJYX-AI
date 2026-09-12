import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../core/theme/tokens.dart';

/// The TRAJYX mark, painted rather than rasterised so it stays crisp at any
/// size and tints with the theme. Matches the web app's inline SVG: a road
/// receding to a vanishing point with a predicted trajectory lifting off it.
class TrajyxMark extends StatelessWidget {
  const TrajyxMark({super.key, this.size = 28});

  final double size;

  @override
  Widget build(BuildContext context) {
    return SizedBox.square(
      dimension: size,
      child: CustomPaint(painter: _MarkPainter()),
    );
  }
}

class _MarkPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    // Drawn on a 32x32 grid, then scaled — keeps the proportions identical to
    // the SVG version regardless of the rendered size.
    final scale = size.width / 32;
    Offset p(double x, double y) => Offset(x * scale, y * scale);

    final roadFill = Paint()
      ..color = TrajyxColors.ink.withValues(alpha: 0.16)
      ..style = PaintingStyle.fill;

    final road = Path()
      ..moveTo(6 * scale, 29 * scale)
      ..lineTo(13.2 * scale, 7 * scale)
      ..lineTo(18.8 * scale, 7 * scale)
      ..lineTo(26 * scale, 29 * scale)
      ..close();
    canvas.drawPath(road, roadFill);

    final edge = Paint()
      ..color = TrajyxColors.ink.withValues(alpha: 0.5)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.4 * scale
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(p(6, 29), p(13.2, 7), edge);
    canvas.drawLine(p(26, 29), p(18.8, 7), edge);

    // Centre dashes shorten with distance to read as perspective.
    final dash = Paint()
      ..color = TrajyxColors.ink.withValues(alpha: 0.42)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.5 * scale
      ..strokeCap = StrokeCap.round;
    const segments = <List<double>>[
      [27.5, 24.0],
      [21.5, 18.8],
      [16.8, 14.7],
      [13.0, 11.4],
      [10.0, 8.9],
    ];
    for (final segment in segments) {
      canvas.drawLine(p(16, segment[0]), p(16, segment[1]), dash);
    }

    // Predicted trajectory — the accent element.
    final trajectory = Paint()
      ..color = TrajyxColors.accent
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.1 * scale
      ..strokeCap = StrokeCap.round;
    final arc = Path()
      ..moveTo(10.5 * scale, 26.5 * scale)
      ..cubicTo(13.5 * scale, 19.5 * scale, 17.5 * scale, 14 * scale, 24.5 * scale, 9.5 * scale);
    canvas.drawPath(arc, trajectory);

    canvas.drawCircle(
      p(24.8, 9.3),
      2.5 * scale,
      Paint()..color = TrajyxColors.accent,
    );
  }

  @override
  bool shouldRepaint(covariant _MarkPainter oldDelegate) => false;
}

/// Wordmark: the mark beside the name, optionally with the descriptor line.
class TrajyxWordmark extends StatelessWidget {
  const TrajyxWordmark({super.key, this.markSize = 26, this.showDescriptor = false});

  final double markSize;
  final bool showDescriptor;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        TrajyxMark(size: markSize),
        const SizedBox(width: Space.sm),
        Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'TRAJYX',
              style: TextStyle(
                color: TrajyxColors.ink,
                fontSize: 17,
                fontWeight: FontWeight.w700,
                letterSpacing: 2.4,
                height: 1,
              ),
            ),
            if (showDescriptor) ...[
              const SizedBox(height: 3),
              Text(
                'PREDICTIVE ROAD SAFETY',
                style: TextStyle(
                  color: TrajyxColors.inkSubtle,
                  fontSize: 8.5,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 1.3,
                  height: 1,
                ),
              ),
            ],
          ],
        ),
      ],
    );
  }
}

/// Rotating-free loading indicator used while the app reaches the API.
class TrajyxLoader extends StatelessWidget {
  const TrajyxLoader({super.key, this.label});

  final String? label;

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Transform.rotate(
          angle: -math.pi / 24,
          child: const SizedBox(
            width: 26,
            height: 26,
            child: CircularProgressIndicator(strokeWidth: 2.4),
          ),
        ),
        if (label != null) ...[
          const SizedBox(height: Space.md),
          Text(label!, style: const TextStyle(color: TrajyxColors.inkSubtle, fontSize: 13)),
        ],
      ],
    );
  }
}
