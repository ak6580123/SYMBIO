/** @type {import('next').NextConfig} */

// The browser talks to the Next server, which proxies /api/* to FastAPI. This
// keeps the frontend free of hardcoded backend hosts and avoids CORS entirely.
const BACKEND = process.env.BACKEND_URL || 'http://localhost:8000';

const nextConfig = {
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${BACKEND}/api/:path*` }];
  },
};

export default nextConfig;
