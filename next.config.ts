import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The floating "N" badge covered the "100 senators tracked" stat on mobile.
  // Hidden in dev too — confusing for screenshot reviews.
  devIndicators: false,
};

export default nextConfig;
