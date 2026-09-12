/**
 * HTTP client for the TRAJYX API.
 *
 * Responsibilities kept deliberately narrow:
 *   - attach the bearer token supplied by the auth layer
 *   - propagate a request id so a browser action can be traced into API logs
 *   - decode the shared error envelope into a typed `ApiError`
 *   - validate responses against a Zod schema when one is supplied
 *
 * It holds no React state and no knowledge of features, so it is usable from
 * tests and from non-React code.
 */

import type { ZodType } from "zod";

import { API_ROOT } from "./env";

/** Shape of `{ "error": { ... } }` as produced by backend/app/core/errors.py. */
export interface ApiErrorBody {
  code: string;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details?: Record<string, unknown>;
  readonly requestId?: string;

  constructor(status: number, body: ApiErrorBody) {
    super(body.message);
    this.name = "ApiError";
    this.status = status;
    this.code = body.code;
    this.details = body.details;
    this.requestId = body.request_id;
  }

  /** True when retrying could plausibly succeed (network blip, cold worker). */
  get isRetryable(): boolean {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }

  /** True when the user must re-authenticate. */
  get isAuthFailure(): boolean {
    return this.status === 401;
  }
}

/** Raised when the API is unreachable, distinct from an API-reported failure. */
export class NetworkError extends ApiError {
  constructor(message: string) {
    super(0, { code: "NETWORK_ERROR", message });
    this.name = "NetworkError";
  }
}

type TokenProvider = () => Promise<string | null> | string | null;

let tokenProvider: TokenProvider = () => null;
let unauthorizedHandler: (() => void) | null = null;

/**
 * Register how the client obtains a bearer token. The auth provider calls this
 * once on mount; the client never reaches into React state itself.
 */
export function setTokenProvider(provider: TokenProvider): void {
  tokenProvider = provider;
}

/** Register a callback invoked on any 401, used to drop the session. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler;
}

export interface RequestOptions<TResponse> {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  /** JSON body. Mutually exclusive with `formData`. */
  body?: unknown;
  /** Multipart body, for video uploads. */
  formData?: FormData;
  /** Query parameters. `undefined` and `null` values are omitted. */
  query?: Record<string, string | number | boolean | undefined | null>;
  /** Validates and narrows the response. Strongly preferred over a bare cast. */
  schema?: ZodType<TResponse>;
  signal?: AbortSignal;
  /** Skip the Authorization header, for the login endpoint itself. */
  anonymous?: boolean;
}

function buildUrl(path: string, query?: RequestOptions<unknown>["query"]): string {
  const url = new URL(`${API_ROOT}${path.startsWith("/") ? path : `/${path}`}`);
  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null) continue;
      url.searchParams.set(key, String(value));
    }
  }
  return url.toString();
}

function newRequestId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

export async function apiRequest<TResponse = unknown>(
  path: string,
  options: RequestOptions<TResponse> = {},
): Promise<TResponse> {
  const { method = "GET", body, formData, query, schema, signal, anonymous } = options;

  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Request-ID": newRequestId(),
  };

  if (!anonymous) {
    const token = await tokenProvider();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let payload: BodyInit | undefined;
  if (formData) {
    // Let the browser set the multipart boundary; setting Content-Type breaks it.
    payload = formData;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(buildUrl(path, query), { method, headers, body: payload, signal });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new NetworkError(
      "Cannot reach the TRAJYX API. Confirm the backend is running and VITE_API_BASE_URL is correct.",
    );
  }

  if (response.status === 401 && !anonymous) unauthorizedHandler?.();

  if (response.status === 204) return undefined as TResponse;

  const text = await response.text();
  let parsed: unknown = null;
  if (text) {
    try {
      parsed = JSON.parse(text);
    } catch {
      // A non-JSON body from a proxy or gateway: surface it as-is, truncated.
      if (!response.ok) {
        throw new ApiError(response.status, {
          code: "MALFORMED_RESPONSE",
          message: text.slice(0, 300) || response.statusText,
        });
      }
    }
  }

  if (!response.ok) {
    const envelope = (parsed as { error?: ApiErrorBody } | null)?.error;
    throw new ApiError(
      response.status,
      envelope ?? { code: "HTTP_ERROR", message: response.statusText || "Request failed." },
    );
  }

  if (!schema) return parsed as TResponse;

  const validated = schema.safeParse(parsed);
  if (!validated.success) {
    // A contract mismatch is a bug, not a user error. Fail loudly and name the route.
    throw new ApiError(response.status, {
      code: "CONTRACT_MISMATCH",
      message: `Response from ${path} did not match the expected schema.`,
      details: { issues: validated.error.issues },
    });
  }
  return validated.data;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions<T>, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, options?: Omit<RequestOptions<T>, "method">) =>
    apiRequest<T>(path, { ...options, method: "POST" }),
  patch: <T>(path: string, options?: Omit<RequestOptions<T>, "method">) =>
    apiRequest<T>(path, { ...options, method: "PATCH" }),
  delete: <T>(path: string, options?: Omit<RequestOptions<T>, "method" | "body">) =>
    apiRequest<T>(path, { ...options, method: "DELETE" }),
};
