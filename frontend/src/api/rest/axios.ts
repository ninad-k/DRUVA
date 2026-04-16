import axios, { AxiosError, type AxiosInstance, type InternalAxiosRequestConfig } from "axios";

/**
 * Central axios instance for REST calls.
 *
 * - Base URL comes from `VITE_REST_URL` (defaults to `/api` via Vite proxy).
 * - Attaches `Authorization: Bearer <access>` from the auth store.
 * - On 401, attempts a single silent refresh; on failure, redirects to login.
 *
 * Token plumbing is deliberately kept here so feature modules never touch tokens.
 */

const baseURL = import.meta.env.VITE_REST_URL ?? "/api";

export const rest: AxiosInstance = axios.create({
  baseURL,
  timeout: 15_000,
});

let accessToken: string | null = null;
let refreshPromise: Promise<string | null> | null = null;

/** Called by the auth store after login / refresh. */
export function setAccessToken(token: string | null) {
  accessToken = token;
}

/** Hook replaced by the auth feature — default redirects to /login. */
export let onAuthFailure = () => {
  window.location.href = "/login";
};

export function registerAuthFailureHandler(fn: () => void) {
  onAuthFailure = fn;
}

/** Replace this with a real refresh call once auth feature is wired. */
export let refreshAccessToken: () => Promise<string | null> = async () => null;

export function registerRefreshFn(fn: () => Promise<string | null>) {
  refreshAccessToken = fn;
}

rest.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return config;
});

rest.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as InternalAxiosRequestConfig & { _retry?: boolean };
    if (error.response?.status !== 401 || original._retry) {
      return Promise.reject(error);
    }
    original._retry = true;
    refreshPromise ??= refreshAccessToken().finally(() => {
      refreshPromise = null;
    });
    const newToken = await refreshPromise;
    if (!newToken) {
      onAuthFailure();
      return Promise.reject(error);
    }
    setAccessToken(newToken);
    original.headers?.set?.("Authorization", `Bearer ${newToken}`);
    return rest(original);
  },
);
