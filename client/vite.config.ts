import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vite';

const dir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  // The game consumes ONLY processed assets. `assets/raw` is never served.
  // Processed output lands at e.g. /player/sheet.png
  publicDir: path.resolve(dir, '../assets/processed'),
  server: {
    port: 5173,
    host: true,
  },
});
