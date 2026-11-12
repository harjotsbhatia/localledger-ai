import type { components } from "./schema";

export type S = components["schemas"];

type BackendInfo = { base_url: string; token: string };

export const isTauri = typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;

let backendInfo: Promise<BackendInfo> | null = null;

function getBackendInfo(): Promise<BackendInfo> {
  if (!backendInfo) {
    const pending: Promise<BackendInfo> = isTauri
      ? import("@tauri-apps/api/core").then(({ invoke }) => invoke<BackendInfo>("get_backend_info"))
      : Promise.resolve({
          base_url: import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8765",
          token: import.meta.env.VITE_BACKEND_TOKEN ?? "",
        });
    // A failed lookup must not be cached, or the app could never recover.
    backendInfo = pending.catch((err) => {
      backendInfo = null;
      throw err;
    });
  }
  return backendInfo;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

export async function api<T>(
  path: string,
  init: { method?: string; body?: unknown; params?: Record<string, string | number | undefined> } = {},
): Promise<T> {
  let info: BackendInfo;
  try {
    info = await getBackendInfo();
  } catch {
    throw new ApiError(0, "backend_unreachable", "The local engine did not start.");
  }
  const { base_url, token } = info;
  const url = new URL(base_url + path);
  for (const [key, value] of Object.entries(init.params ?? {})) {
    if (value !== undefined && value !== "") url.searchParams.set(key, String(value));
  }
  let response: Response;
  try {
    response = await fetch(url, {
      method: init.method ?? "GET",
      headers: {
        Authorization: `Bearer ${token}`,
        ...(init.body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: init.body !== undefined ? JSON.stringify(init.body) : undefined,
      credentials: "omit",
    });
  } catch (err) {
    if (isTauri && import.meta.env.DEV) {
      const { invoke } = await import("@tauri-apps/api/core");
      void invoke("debug_log", { message: `fetch ${path} failed: ${String(err)} (page ${location.origin})` });
    }
    throw new ApiError(0, "backend_unreachable", "The local engine is not responding.");
  }
  if (response.status === 204) return undefined as T;
  const data: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      const d = detail as { code?: string; message: string };
      throw new ApiError(response.status, d.code ?? "error", d.message);
    }
    throw new ApiError(response.status, "error", typeof detail === "string" ? detail : "Request failed.");
  }
  return data as T;
}

export type StatementFile = { name: string; content: string };

/** Native macOS open panel inside the app; a plain file input when running in a browser. */
export async function pickStatement(): Promise<StatementFile | null> {
  if (isTauri) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<StatementFile | null>("pick_statement_file");
  }
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".csv,.tsv,.txt";
    input.onchange = async () => {
      const file = input.files?.[0];
      resolve(file ? { name: file.name, content: await file.text() } : null);
    };
    input.oncancel = () => resolve(null);
    input.click();
  });
}
