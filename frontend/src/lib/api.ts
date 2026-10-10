// Thin client for the EvoLab backend (docs/API.md). All calls go to /api/v1 on this
// origin; next.config.mjs proxies them to the backend, so the session cookie just works.

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type Method = "GET" | "POST" | "PUT" | "DELETE";

export async function api<T>(path: string, method: Method = "GET", body?: unknown): Promise<T> {
  const res = await fetch(`/api/v1${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : undefined,
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (res.status === 401 && typeof window !== "undefined" && !path.startsWith("/auth/")) {
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
  }
  if (!res.ok) {
    let code = "error";
    let message = res.statusText;
    try {
      const data = await res.json();
      code = data?.error?.code ?? code;
      message = data?.error?.message ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, code, message);
  }
  if (res.status === 204) return undefined as T;
  const text = await res.text();
  return (text ? JSON.parse(text) : undefined) as T;
}

export async function uploadInput(projectId: string, kind: string, file: File) {
  const form = new FormData();
  form.append("kind", kind);
  form.append("file", file);
  const res = await fetch(`/api/v1/projects/${projectId}/inputs`, { method: "POST", body: form, credentials: "same-origin" });
  if (!res.ok) throw new ApiError(res.status, "upload_failed", (await res.text()).slice(0, 200));
  return res.json();
}
