import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The floating "N" badge covered the "100 senators tracked" stat on mobile.
  // Hidden in dev too — confusing for screenshot reviews.
  devIndicators: false,
  // Texas got promoted from /states/tx to a top-level /texas section. Keep
  // any old links working with permanent redirects.
  async redirects() {
    return [
      { source: "/states/tx", destination: "/texas", permanent: true },
      { source: "/states/tx/:id", destination: "/texas/:id", permanent: true },
    ];
  },
};

export default nextConfig;
