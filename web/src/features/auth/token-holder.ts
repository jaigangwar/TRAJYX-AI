/**
 * The current bearer token, held outside React.
 *
 * The API client needs the token synchronously, from non-React code, and the
 * token is not render state — no component displays it, and changing it does
 * not change any output. Keeping it in a ref meant reading that ref during
 * render to keep the client in step, which is exactly the pattern React warns
 * about.
 *
 * So it lives here: a single module-scoped value, written by the auth provider
 * from event handlers and effects, read by the API client on each request.
 */

let currentToken: string | null = null;

export function setAuthToken(token: string | null): void {
  currentToken = token;
}

export function getAuthToken(): string | null {
  return currentToken;
}
