import type { NextConfig } from "next";

// The FastAPI back end (uv run uvicorn conformscope.api:app). The browser only ever
// talks to /api/*, so model keys stay on the server.
const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  experimental: {
    // Reading a plan with Muse Spark can take longer than the 30 s default.
    proxyTimeout: 120_000,
  },
  rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
