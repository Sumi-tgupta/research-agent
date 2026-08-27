import bundleAnalyzer from "@next/bundle-analyzer";

// Opt-in bundle analysis: `ANALYZE=true npm run build` opens treemaps in the
// browser. When ANALYZE is unset, this wrapper returns the config untouched, so
// normal builds are unaffected.
const withBundleAnalyzer = bundleAnalyzer({
  enabled: process.env.ANALYZE === "true",
});

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // We can't run a lint pass in this build environment; don't let lint
  // warnings block `next build`. Type-checking still runs.
  eslint: { ignoreDuringBuilds: true },
  experimental: {
    // Rewrite barrel imports to direct paths so we only ship the icons/charts
    // we actually use. Safe, reversible tree-shaking hint. (lucide-react is
    // optimized by default in 14.2; listed for clarity alongside recharts.)
    optimizePackageImports: ["lucide-react", "recharts"],
  },
};

export default withBundleAnalyzer(nextConfig);
