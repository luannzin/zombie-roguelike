/** Promise wrapper around `Image.onload`. Shared by every asset loader. */
export function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`failed to load ${src}`));
    img.src = src;
  });
}

/** Fetch JSON, failing loudly on a non-2xx instead of parsing an error page. */
export async function loadJson<T>(src: string): Promise<T> {
  const response = await fetch(src);
  if (!response.ok) throw new Error(`${src}: ${response.status}`);
  return (await response.json()) as T;
}
