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

const isDev = process.env.NODE_ENV === "development";

/**
 * Content-Security-Policy for pages (ADR-050). Nonces are not used: they require fully dynamic
 * rendering, which Cache Components / partial prerendering do not allow, so inline scripts
 * from Next.js are permitted with 'unsafe-inline'. Everything else is same-origin only, the
 * app cannot be framed and no plugins, foreign forms or base-URL changes are allowed. React
 * escapes all rendered text and the code never injects raw HTML.
 */
const contentSecurityPolicy = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  `connect-src 'self'${isDev ? " ws: wss:" : ""}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
].join("; ");

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  // The dev server only trusts `localhost` by default; local URLs use 127.0.0.1 (ADR-015).
  allowedDevOrigins: ["127.0.0.1"],
  cacheComponents: true,
  experimental: {
    // The /api rewrite buffers request bodies (default 10 MB). Match Nginx's
    // client_max_body_size so document uploads up to UPLOAD_MAX_BYTES (25 MB) pass through;
    // the backend enforces the real limit.
    proxyClientMaxBodySize: "30mb",
  },
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async redirects() {
    // The dashboard is the home page of the signed-in application.
    return [{ source: "/", destination: "/dashboard", permanent: false }];
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
          { key: "Content-Security-Policy", value: contentSecurityPolicy },
          {
            key: "Permissions-Policy",
            value: "camera=(), microphone=(), geolocation=(), payment=()",
          },
        ],
      },
    ];
  },
};

export default nextConfig;
