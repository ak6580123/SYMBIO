/** @type {import('next').NextConfig} */

// The browser talks to the Next server, which proxies /api/* to FastAPI. This
// keeps the frontend free of hardcoded backend hosts and avoids CORS entirely.
const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000';

// Next.js caps proxied requests at 30s *in development* (see
// next/dist/server/lib/router-utils/proxy-request.js: `proxyTimeout || 30000`).
// POST /api/analyze waits on local Ollama, and qwen2.5:3b on CPU routinely
// needs longer than 30s - the proxy then aborted the upstream socket and the
// browser saw an opaque 500 while the terminal logged
// "Failed to proxy ... socket hang up / ECONNRESET".
//
// Keep this comfortably above OLLAMA_TIMEOUT_SECONDS (default 60) so FastAPI
// always gets to answer - including with its deterministic fallback - instead
// of being cut off mid-inference.
const PROXY_TIMEOUT_MS = Number(process.env.PROXY_TIMEOUT_MS || 120000);

const nextConfig = {
  experimental: {
    proxyTimeout: PROXY_TIMEOUT_MS,
  },
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
