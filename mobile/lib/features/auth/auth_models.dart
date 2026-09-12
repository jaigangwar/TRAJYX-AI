import '../../core/contracts/domain.dart';

/// A TRAJYX account as returned by the API.
class AuthUser {
  const AuthUser({
    required this.id,
    required this.email,
    required this.role,
    this.displayName,
    this.status = 'active',
  });

  factory AuthUser.fromJson(Map<String, dynamic> json) {
    return AuthUser(
      id: json['id'] as String,
      email: json['email'] as String? ?? '',
      // An unrecognised role must never fail open to something privileged.
      role: Role.tryParse(json['role'] as String?) ?? Role.driver,
      displayName: json['display_name'] as String?,
      status: json['status'] as String? ?? 'active',
    );
  }

  final String id;
  final String email;
  final Role role;
  final String? displayName;
  final String status;

  bool get isActive => status == 'active';

  /// The driver app is for drivers; staff use the web console. Administrators
  /// are allowed through so a deployment can be checked from one account.
  bool get canUseDriverApp => role == Role.driver || role == Role.admin;

  String get label => displayName?.isNotEmpty == true ? displayName! : email;

  Map<String, dynamic> toJson() => {
        'id': id,
        'email': email,
        'role': role.wire,
        'display_name': displayName,
        'status': status,
      };
}

/// A stored session: the token, the profile it belonged to, and its deadline.
class AuthSession {
  const AuthSession({required this.token, required this.user, required this.expiresAt});

  factory AuthSession.fromJson(Map<String, dynamic> json) {
    return AuthSession(
      token: json['token'] as String,
      user: AuthUser.fromJson(json['user'] as Map<String, dynamic>),
      expiresAt: DateTime.parse(json['expires_at'] as String),
    );
  }

  final String token;
  final AuthUser user;
  final DateTime expiresAt;

  /// Treated as expired slightly early, so a token is not sent mid-flight.
  bool get isExpired => DateTime.now().isAfter(expiresAt.subtract(const Duration(seconds: 30)));

  Map<String, dynamic> toJson() => {
        'token': token,
        'user': user.toJson(),
        'expires_at': expiresAt.toIso8601String(),
      };
}

/// What the UI needs to know about the session, as one value.
sealed class AuthState {
  const AuthState();
}

/// Restoring and verifying a stored session. The app shows a splash.
class AuthRestoring extends AuthState {
  const AuthRestoring();
}

class AuthSignedOut extends AuthState {
  const AuthSignedOut({this.message});

  /// Explains an involuntary sign-out, e.g. a suspended account.
  final String? message;
}

class AuthSignedIn extends AuthState {
  const AuthSignedIn(this.session);

  final AuthSession session;

  AuthUser get user => session.user;
}
