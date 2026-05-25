/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@ai-recruitment/types", "@ai-recruitment/utils"],
  experimental: {
    optimizePackageImports: ["lucide-react", "recharts"],
  },
};

module.exports = nextConfig;
