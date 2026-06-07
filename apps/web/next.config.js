/** @type {import('next').NextConfig} */
const API_URL = process.env.API_URL || "http://localhost:8000";

const nextConfig = {
  transpilePackages: ["@ai-recruitment/types", "@ai-recruitment/utils"],
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts"],
  },
  // B6: reverse proxy /api/v1/* 到 backend, 让 Playwright e2e setup 走 frontend → backend 路径
  async rewrites() {
    return [
      { source: "/api/v1/:path*", destination: `${API_URL}/api/v1/:path*` },
    ];
  },
};

module.exports = nextConfig;
