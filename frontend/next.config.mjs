/** @type {import('next').NextConfig} */
// The browser talks only to this Next.js server; /api/v1/* is proxied to the backend.
// Same origin means the HttpOnly session cookie and the live event stream (SSE) work without CORS.
const BACKEND_URL = process.env.EVOLAB_BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig = {
  reactStrictMode: true,
  compress: false, // keep the event stream unbuffered through the proxy
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${BACKEND_URL}/api/v1/:path*` }];
  },
};

export default nextConfig;
