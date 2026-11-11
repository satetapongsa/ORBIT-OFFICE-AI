import type { NextConfig } from "next";

/**
 * The browser always calls the API on its own origin (`/api/v1/...`).
 * - Development: Next.js rewrites `/api/*` to the FastAPI backend.
 * - Production: Nginx routes `/api/*` to the backend before it reaches Next.js.
 *
 * BACKEND_INTERNAL_URL is server-side only and is read when the server starts
 * (`next dev`) or at build time (`next build` / standalone output).
 */
const backendUrl = (process.env.BACKEND_INTERNAL_URL ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // The dev server only trusts `localhost` by default; local URLs use 127.0.0.1 (ADR-015).
  allowedDevOrigins: ["127.0.0.1"],
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        ],
      },
    ];
  },
};

export default nextConfig;
