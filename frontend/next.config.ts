import type { NextConfig } from "next";

/**
 * The browser always calls the API on its own origin (`/api/v1/...`).
 * - Development: Next.js rewrites `/api/*` to the FastAPI backend.
 * - Production: Nginx routes `/api/*` to the backend before it reaches Next.js.
 *
 * BACKEND_INTERNAL_URL is server-side only and is read when the server starts
 * (`next dev`) or at build time (`next build` / standalone output).
 */
const backendUrl = (process.env.BACKEND_INTERNAL_URL ?? "http://localhost:8000").replace(/\/$/, "");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
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
