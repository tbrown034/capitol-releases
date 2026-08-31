import type { MetadataRoute } from "next";
import {
  getActiveSenatorIds,
  getReleaseIdsForSitemap,
} from "./lib/queries";
import { SITE_URL } from "./lib/site";

// Google caps each sitemap file at 50,000 URLs and the corpus (~105k
// eligible releases, growing daily) blew past a single file — the old
// one-file version silently truncated at exactly its 49k budget and
// dropped every Texas release. Sharded via generateSitemaps():
//   /sitemap/0.xml  — static pages + all member pages
//   /sitemap/1.xml+ — releases, RELEASES_PER_SHARD per file, newest first
// The shard list is fixed and over-provisioned (4 release shards = 180k
// capacity); an empty trailing shard is valid and harmless. robots.ts
// lists all shard URLs. Bump RELEASE_SHARDS when the corpus approaches
// RELEASES_PER_SHARD * RELEASE_SHARDS.
const RELEASES_PER_SHARD = 45_000;
const RELEASE_SHARDS = 4;

export const revalidate = 3600;

export async function generateSitemaps() {
  return Array.from({ length: RELEASE_SHARDS + 1 }, (_, id) => ({ id }));
}

export default async function sitemap(props: {
  id: Promise<string>;
}): Promise<MetadataRoute.Sitemap> {
  const id = Number(await props.id);
  const now = new Date();

  if (id === 0) {
    const staticPaths = [
      { path: "/", changeFrequency: "daily" as const, priority: 1.0 },
      { path: "/feed", changeFrequency: "hourly" as const, priority: 0.9 },
      { path: "/trending", changeFrequency: "hourly" as const, priority: 0.8 },
      { path: "/senators", changeFrequency: "daily" as const, priority: 0.8 },
      { path: "/house", changeFrequency: "daily" as const, priority: 0.8 },
      { path: "/search", changeFrequency: "weekly" as const, priority: 0.6 },
      { path: "/about", changeFrequency: "monthly" as const, priority: 0.4 },
      { path: "/status", changeFrequency: "daily" as const, priority: 0.3 },
      // Texas Senate section
      { path: "/texas", changeFrequency: "daily" as const, priority: 0.8 },
      { path: "/texas/feed", changeFrequency: "daily" as const, priority: 0.7 },
      { path: "/texas/search", changeFrequency: "weekly" as const, priority: 0.5 },
      { path: "/texas/trending", changeFrequency: "weekly" as const, priority: 0.5 },
    ];

    const [officialIds, txSenatorIds, houseMemberIds] = await Promise.all([
      getActiveSenatorIds("us-senate"),
      getActiveSenatorIds("tx-senate"),
      getActiveSenatorIds("us-house"),
    ]);

    return [
      ...staticPaths.map((p) => ({
        url: `${SITE_URL}${p.path}`,
        lastModified: now,
        changeFrequency: p.changeFrequency,
        priority: p.priority,
      })),
      ...officialIds.map((sid) => ({
        url: `${SITE_URL}/senators/${sid}`,
        lastModified: now,
        changeFrequency: "daily" as const,
        priority: 0.7,
      })),
      ...houseMemberIds.map((mid) => ({
        url: `${SITE_URL}/house/${mid}`,
        lastModified: now,
        changeFrequency: "daily" as const,
        priority: 0.6,
      })),
      ...txSenatorIds.map((sid) => ({
        url: `${SITE_URL}/texas/${sid}`,
        lastModified: now,
        changeFrequency: "daily" as const,
        priority: 0.6,
      })),
    ];
  }

  const releases = await getReleaseIdsForSitemap(
    (id - 1) * RELEASES_PER_SHARD,
    RELEASES_PER_SHARD
  );

  return releases.map((r) => ({
    url: `${SITE_URL}/releases/${r.id}`,
    lastModified: r.updated_at ? new Date(r.updated_at) : now,
    changeFrequency: "monthly" as const,
    priority: 0.6,
  }));
}
