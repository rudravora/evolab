/** @type {import('next').NextConfig} */
// The browser talks only to this Next.js server; /api/v1/* is proxied to the backend.
// Same origin means the HttpOnly session cookie and the live event stream (SSE) work without CORS.
const BACKEND_URL = process.env.EVOLAB_BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig = {
  // A second dev server (for example one pointed at the simulated backend) needs its own build folder.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactStrictMode: true,
  // Import only the icons used, not the whole library (keeps dev compiles fast).
  experimental: { optimizePackageImports: ["@phosphor-icons/react"] },
  compress: false, // keep the event stream unbuffered through the proxy
  // The workspace used to live under /v2 while it was being built; keep old links working.
  async redirects() {
    return [
      { source: "/v2", destination: "/dashboard", permanent: false },
      { source: "/v2/:path*", destination: "/:path*", permanent: false },
    ];
  },
  async rewrites() {
    return [{ source: "/api/v1/:path*", destination: `${BACKEND_URL}/api/v1/:path*` }];
  },
};

export default nextConfig;
