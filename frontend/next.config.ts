import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactCompiler: true,
  async redirects() {
    return [
      { source: "/planner", destination: "/planner/workspace/high-rise", permanent: false },
      { source: "/planner/site-plan", destination: "/planner/workspace/high-rise", permanent: false },
    ];
  },
};

export default nextConfig;
