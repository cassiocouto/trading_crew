import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Emit a self-contained server bundle so the Docker image does not need
  // a full node_modules tree at runtime (see dashboard/Dockerfile).
  output: "standalone",

  devIndicators: false,
};

export default nextConfig;
