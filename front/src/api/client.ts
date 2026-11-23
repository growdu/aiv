/** 接口面的小客户端——**只认这一个前缀**。
 *
 * 全仓库里 `/api` 这个前缀只在这一个文件里出现一次（`BASE`）。
 * 视图层要拿数据，一律走这里的函数，不许自己拼地址。
 */

/** 接口面的前缀。 */
const BASE = "/api";

/** 路径归一：写 `/documents` 或 `/api/documents` 都成，结果一样。 */
function endpoint(path: string): string {
  if (!path.startsWith("/")) {
    throw new Error(`路径要以 / 开头：${path}`);
  }
  return path === BASE || path.startsWith(`${BASE}/`) ? path : `${BASE}${path}`;
}

async function request<T>(url: string, init: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${await response.text()}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/** 取一份 JSON。 */
export async function getJSON<T>(path: string): Promise<T> {
  return request<T>(endpoint(path), { method: "GET" });
}

/** 送一份 JSON，拿到一份 JSON。 */
export async function postJSON<T>(path: string, body?: unknown): Promise<T> {
  return request<T>(endpoint(path), {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

/** 改一份 JSON，拿到一份 JSON。 */
export async function putJSON<T>(path: string, body: unknown): Promise<T> {
  return request<T>(endpoint(path), {
    method: "PUT",
    body: JSON.stringify(body),
  });
}

/** 产物的地址。**不 encodeURIComponent**——`artifact_id` 是 posix 路径，斜杠要留着。 */
export function artifactURL(artifactId: string): string {
  return `${BASE}/artifacts/${artifactId}`;
}

/** 作业事件流的地址。 */
export function eventURL(jobId: string): string {
  return `${BASE}/jobs/${jobId}/events`;
}
