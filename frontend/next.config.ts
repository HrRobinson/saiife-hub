import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

// The API origin the browser may call. NEXT_PUBLIC_* is inlined at BUILD time, so
// each environment builds its own image (see cloudbuild.yaml).
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "https://api.saiife.localhost:8000";

// Next emits inline <script> for the RSC payload and the next-themes FOUC script,
// so 'unsafe-inline' is required for hydration. 'unsafe-eval' is dev-only (HMR).
const csp = [
  "default-src 'self'",
  isDev ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'" : "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: https:",
  `connect-src 'self' ${apiUrl}` + (isDev ? " ws: wss:" : ""),
  "frame-ancestors 'none'",
  "base-uri 'self'",
  "form-action 'self'",
].join("; ");

const config: NextConfig = {
  output: "standalone",
  reactStrictMode: true,
  typedRoutes: true,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
    ];
  },
};

export default config;
