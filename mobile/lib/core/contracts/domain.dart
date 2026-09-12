// TRAJYX generated file - DO NOT EDIT BY HAND.
// Source: shared/contracts/domain.json
// Regenerate: python scripts/gen_contracts.py

const String kContractVersion = '1.0.0';

/// Authorization roles. Ordered from most to least privileged.
enum Role {
  admin('ADMIN'),
  trafficOperator('TRAFFIC_OPERATOR'),
  analyst('ANALYST'),
  driver('DRIVER'),
  ;

  const Role(this.wire);
  final String wire;

  static Role? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in Role.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Coarse risk band derived from a 0-100 risk score.
enum RiskLevel {
  low('LOW'),
  moderate('MODERATE'),
  high('HIGH'),
  critical('CRITICAL'),
  ;

  const RiskLevel(this.wire);
  final String wire;

  static RiskLevel? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in RiskLevel.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Event severity, independent of the numeric risk score.
enum Severity {
  info('INFO'),
  minor('MINOR'),
  major('MAJOR'),
  critical('CRITICAL'),
  ;

  const Severity(this.wire);
  final String wire;

  static Severity? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in Severity.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Canonical event taxonomy emitted by the safety, interaction and risk engines.
enum EventType {
  helmetViolation('HELMET_VIOLATION'),
  seatbeltViolation('SEATBELT_VIOLATION'),
  tripleRiding('TRIPLE_RIDING'),
  wrongWay('WRONG_WAY'),
  redLightViolation('RED_LIGHT_VIOLATION'),
  stopLineViolation('STOP_LINE_VIOLATION'),
  dangerousLaneChange('DANGEROUS_LANE_CHANGE'),
  overspeed('OVERSPEED'),
  hardBraking('HARD_BRAKING'),
  suddenAcceleration('SUDDEN_ACCELERATION'),
  distractedRiding('DISTRACTED_RIDING'),
  pedestrianConflict('PEDESTRIAN_CONFLICT'),
  nearMiss('NEAR_MISS'),
  collisionRisk('COLLISION_RISK'),
  hazardReport('HAZARD_REPORT'),
  ;

  const EventType(this.wire);
  final String wire;

  static EventType? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in EventType.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Grouping used by dashboard navigation and reporting.
enum EventCategory {
  violation('VIOLATION'),
  behavior('BEHAVIOR'),
  interaction('INTERACTION'),
  report('REPORT'),
  ;

  const EventCategory(this.wire);
  final String wire;

  static EventCategory? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in EventCategory.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Detector output classes. Extend by adding here and retraining/remapping the detector.
enum VehicleClass {
  car('CAR'),
  motorcycle('MOTORCYCLE'),
  scooter('SCOOTER'),
  bus('BUS'),
  truck('TRUCK'),
  autoRickshaw('AUTO_RICKSHAW'),
  van('VAN'),
  bicycle('BICYCLE'),
  pedestrian('PEDESTRIAN'),
  ;

  const VehicleClass(this.wire);
  final String wire;

  static VehicleClass? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in VehicleClass.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Operational state of a camera as shown in Live Monitoring.
enum CameraStatus {
  online('ONLINE'),
  offline('OFFLINE'),
  processing('PROCESSING'),
  alert('ALERT'),
  ;

  const CameraStatus(this.wire);
  final String wire;

  static CameraStatus? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in CameraStatus.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Lifecycle of an asynchronous video analysis job.
enum JobStatus {
  queued('QUEUED'),
  processing('PROCESSING'),
  completed('COMPLETED'),
  failed('FAILED'),
  cancelled('CANCELLED'),
  ;

  const JobStatus(this.wire);
  final String wire;

  static JobStatus? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in JobStatus.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Band for an ESTIMATED time-to-collision value. Always presented as an estimate.
enum TtcBand {
  low('LOW'),
  medium('MEDIUM'),
  high('HIGH'),
  critical('CRITICAL'),
  ;

  const TtcBand(this.wire);
  final String wire;

  static TtcBand? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in TtcBand.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Tri-state result for any visual check. UNABLE_TO_DETERMINE is a first-class outcome and must never be collapsed into a negative.
enum Determination {
  detected('DETECTED'),
  notDetected('NOT_DETECTED'),
  unableToDetermine('UNABLE_TO_DETERMINE'),
  ;

  const Determination(this.wire);
  final String wire;

  static Determination? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in Determination.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Driver alert escalation tiers.
enum AlertLevel {
  level1('LEVEL_1'),
  level2('LEVEL_2'),
  level3('LEVEL_3'),
  ;

  const AlertLevel(this.wire);
  final String wire;

  static AlertLevel? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in AlertLevel.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Provenance label. Every record carries one so simulated and estimated values are never displayed as measured ground truth.
enum DataOrigin {
  measured('MEASURED'),
  estimated('ESTIMATED'),
  demo('DEMO'),
  ;

  const DataOrigin(this.wire);
  final String wire;

  static DataOrigin? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in DataOrigin.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Hazard categories a driver can report from the mobile app.
enum HazardType {
  accident('ACCIDENT'),
  pothole('POTHOLE'),
  brokenSignal('BROKEN_SIGNAL'),
  roadBlockage('ROAD_BLOCKAGE'),
  wrongWayVehicle('WRONG_WAY_VEHICLE'),
  dangerousCrossing('DANGEROUS_CROSSING'),
  poorVisibility('POOR_VISIBILITY'),
  roadDamage('ROAD_DAMAGE'),
  other('OTHER'),
  ;

  const HazardType(this.wire);
  final String wire;

  static HazardType? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in HazardType.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Review workflow state for driver hazard reports and flagged violations.
enum ReportStatus {
  pending('PENDING'),
  reviewing('REVIEWING'),
  confirmed('CONFIRMED'),
  rejected('REJECTED'),
  ;

  const ReportStatus(this.wire);
  final String wire;

  static ReportStatus? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in ReportStatus.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Operational health of a registered model version.
enum ModelHealth {
  healthy('HEALTHY'),
  warning('WARNING'),
  needsAttention('NEEDS_ATTENTION'),
  unknown('UNKNOWN'),
  ;

  const ModelHealth(this.wire);
  final String wire;

  static ModelHealth? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in ModelHealth.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

/// Traffic signal phase used by the red-light violation detector. UNKNOWN suppresses red-light detection entirely.
enum SignalState {
  red('RED'),
  amber('AMBER'),
  green('GREEN'),
  unknown('UNKNOWN'),
  ;

  const SignalState(this.wire);
  final String wire;

  static SignalState? tryParse(String? value) {
    if (value == null) return null;
    for (final entry in SignalState.values) {
      if (entry.wire == value) return entry;
    }
    return null;
  }
}

class RiskBand {
  const RiskBand(this.level, this.min, this.max);

  final RiskLevel level;
  final int min;
  final int max;
}

const List<RiskBand> kRiskBands = [
  RiskBand(RiskLevel.low, 0, 25),
  RiskBand(RiskLevel.moderate, 26, 50),
  RiskBand(RiskLevel.high, 51, 75),
  RiskBand(RiskLevel.critical, 76, 100),
];

/// Map a 0-100 risk score onto its band. Scores are clamped into range.
RiskLevel riskLevelFromScore(num score) {
  final s = score.clamp(0, 100);
  for (final band in kRiskBands) {
    if (s <= band.max) return band.level;
  }
  return RiskLevel.critical;
}
