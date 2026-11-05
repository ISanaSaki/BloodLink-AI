import { API_BASE_URL, USE_MOCK, TOKEN_KEY } from "./config.js";
import { mockRequest, MockApiError } from "./mock-api.js";

export class ApiError extends Error {
  constructor(message, { code = "NETWORK_ERROR", status = 0, details = [], requestId = "" } = {}) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.details = details;
    this.requestId = requestId;
  }
}

let redirecting = false;

export function getToken() {
  return sessionStorage.getItem(TOKEN_KEY);
}

export function setToken(token) {
  if (token) sessionStorage.setItem(TOKEN_KEY, token);
  else sessionStorage.removeItem(TOKEN_KEY);
}

function handleUnauthorized() {
  setToken(null);
  sessionStorage.removeItem("blood_user");
  if (redirecting) return;
  redirecting = true;
  const target = new URL("../pages/login.html", import.meta.url);
  target.searchParams.set("next", location.pathname.split("/").pop() || "index.html");
  location.replace(target);
}

async function parseJson(response) {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

export async function apiRequest(path, { method = "GET", body, auth = true, signal } = {}) {
  const token = getToken();

  if (USE_MOCK) {
    try {
      const { payload } = await mockRequest(path, { method, body, token: auth ? token : null });
      return payload;
    } catch (error) {
      if (error instanceof MockApiError) {
        if (error.status === 401 && auth) handleUnauthorized();
        throw new ApiError(error.message, {
          code: error.code,
          status: error.status,
          details: error.details,
          requestId: error.requestId,
        });
      }
      throw error;
    }
  }

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      signal,
      headers: {
        Accept: "application/json",
        ...(body ? { "Content-Type": "application/json" } : {}),
        ...(auth && token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: body ? JSON.stringify(body) : undefined,
    });
  } catch (error) {
    if (error.name === "AbortError") throw error;
    throw new ApiError("ارتباط با سرور برقرار نشد. اتصال اینترنت را بررسی کنید.");
  }

  const payload = await parseJson(response);

  if (response.status === 401 && auth) handleUnauthorized();

  if (!response.ok || payload?.error) {
    const apiError = payload?.error ?? {};
    throw new ApiError(apiError.message || "خطایی در پردازش درخواست رخ داد.", {
      code: apiError.code || `HTTP_${response.status}`,
      status: response.status,
      details: apiError.details || [],
      requestId: apiError.request_id || "",
    });
  }

  return payload;
}

export const api = {
  get: (path, options) => apiRequest(path, { ...options, method: "GET" }),
  post: (path, body, options) => apiRequest(path, { ...options, method: "POST", body }),
  patch: (path, body, options) => apiRequest(path, { ...options, method: "PATCH", body }),
  delete: (path, options) => apiRequest(path, { ...options, method: "DELETE" }),
};
