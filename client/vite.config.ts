import path from 'node:path';
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const dir = path.dirname(fileURLToPath(import.meta.url));

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // The game consumes ONLY processed assets. `assets/raw` is never served.
  // Processed output lands at e.g. /player/sheet.png
  publicDir: path.resolve(dir, '../assets/processed'),
  resolve: {
    alias: { '@': path.resolve(dir, 'src') },
  },
  server: {
    port: 5173,
    host: true,
  },
});
