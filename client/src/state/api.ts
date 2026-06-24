import { GATEWAY_URL } from "./session";
async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`API ${res.status}: ${await res.text()}`);
  return (await res.json()) as T;
}
export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return handle<T>(await fetch(`${GATEWAY_URL}${path}`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }));
}
export async function apiGet<T>(path: string): Promise<T> {
  return handle<T>(await fetch(`${GATEWAY_URL}${path}`));
}
