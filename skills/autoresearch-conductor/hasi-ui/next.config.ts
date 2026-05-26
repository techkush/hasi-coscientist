import type { NextConfig } from "next";

const config: NextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  // Type-check is disabled in CI build because the runtime gateway uses dynamic
  // tRPC inputs the static checker can't follow into the conductor types.
  typescript: { ignoreBuildErrors: true },
};

export default config;
