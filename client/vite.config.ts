import path from 'node:path';
import { fileURLToPath } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const dir = path.dirname(fileURLToPath(import.meta.url));

// Same-origin API so a phone on the LAN only needs :5173. Uvicorn stays on loopback.
const api = {
  '/rooms': 'http://127.0.0.1:8000',
  '/health': 'http://127.0.0.1:8000',
  '/ws': { target: 'http://127.0.0.1:8000', ws: true },
};

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
    proxy: api,
  },
  preview: {
    host: true,
    proxy: api,
  },
});
