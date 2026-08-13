/**
 * Where the server is. One base origin, two derived URLs.
 *
 * Default is the page origin: Vite proxies `/rooms`, `/health` and `/ws` to
 * uvicorn on loopback, so a LAN client only needs the Vite URL.
 *
 * `VITE_SERVER_URL` is an HTTP origin (`http://192.168.0.10:8000`), not a
 * socket URL: the room socket is one of several endpoints now, and deriving
 * `ws://` from `http://` is safer than the other way round.
 */

function base(): string {
  const env = import.meta.env.VITE_SERVER_URL as string | undefined;
  if (env) return env.replace(/\/+$/, '');
  return location.origin;
}

export function httpUrl(path: string): string {
  return `${base()}${path}`;
}

/** The room socket, with the name the player chose in the menu. */
export function roomSocketUrl(code: string, name: string): string {
  const url = new URL(`/ws/${encodeURIComponent(code)}`, base());
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  url.searchParams.set('name', name);
  return url.toString();
}
