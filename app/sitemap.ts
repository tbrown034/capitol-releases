import type { MetadataRoute } from "next";
import {
  getActiveSenatorIds,
  getReleaseCountForSitemap,
  getReleaseIdsForSitemap,
} from "./lib/queries";
import { SITE_URL } from "./lib/site";

// Google caps each sitemap at 50,000 URLs. The corpus is ~30k releases plus
// 100 senators plus a handful of static pages, so one file fits. Bump to
// generateSitemaps() if/when we cross the cap.
const MAX_URLS = 49_000;

export const revalidate = 3600;

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const now = new Date();

  const staticPaths = [
    { path: "/", changeFrequency: "daily" as const, priority: 1.0 },
    { path: "/feed", changeFrequency: "hourly" as const, priority: 0.9 },
    { path: "/trending", changeFrequency: "hourly" as const, priority: 0.8 },
    { path: "/senators", changeFrequency: "daily" as const, priority: 0.8 },
    { path: "/search", changeFrequency: "weekly" as const, priority: 0.6 },
    { path: "/about", changeFrequency: "monthly" as const, priority: 0.4 },
    { path: "/deleted", changeFrequency: "daily" as const, priority: 0.5 },
    { path: "/status", changeFrequency: "daily" as const, priority: 0.3 },
  ];

  const [senatorIds, total] = await Promise.all([
    getActiveSenatorIds(),
    getReleaseCountForSitemap(),
  ]);

  const headerEntries: MetadataRoute.Sitemap = [
    ...staticPaths.map((p) => ({
      url: `${SITE_URL}${p.path}`,
      lastModified: now,
      changeFrequency: p.changeFrequency,
      priority: p.priority,
    })),
    ...senatorIds.map((sid) => ({
      url: `${SITE_URL}/senators/${sid}`,
      lastModified: now,
      changeFrequency: "daily" as const,
      priority: 0.7,
    })),
  ];

  const releaseBudget = Math.max(0, MAX_URLS - headerEntries.length);
  const limit = Math.min(total, releaseBudget);
  const releases = limit > 0 ? await getReleaseIdsForSitemap(0, limit) : [];

  return [
    ...headerEntries,
    ...releases.map((r) => ({
      url: `${SITE_URL}/releases/${r.id}`,
      lastModified: r.updated_at ? new Date(r.updated_at) : now,
      changeFrequency: "monthly" as const,
      priority: 0.6,
    })),
  ];
}
