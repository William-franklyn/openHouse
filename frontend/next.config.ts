import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Every route here is inherently dynamic (auth comes from localStorage,
  // chat state is realtime) - cacheComponents' prerendering model has
  // nothing to offer this app and broke /room/[id] (params accessed
  // outside <Suspense>), so it's off rather than architected around.
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
