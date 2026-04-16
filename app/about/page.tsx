import { getStats, getSenators } from "../lib/queries";

export const metadata = {
  title: "About -- Capitol Releases",
  description: "Methodology, data sources, and technical approach behind Capitol Releases.",
};

export default async function AboutPage() {
  const stats = await getStats();
  const senators = await getSenators();

  // Compute parser family distribution from senators with releases
  const familyCounts: Record<string, number> = {};
  for (const s of senators) {
    const fam = s.parser_family ?? "unknown";
    familyCounts[fam] = (familyCounts[fam] ?? 0) + 1;
  }
  const sortedFamilies = Object.entries(familyCounts).sort(
    (a, b) => b[1] - a[1]
  );

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-3xl font-bold">About Capitol Releases</h1>
      <p className="mt-3 text-gray-600 leading-relaxed">
        Capitol Releases is a journalism and public-records project that builds
        a normalized, searchable archive of official press releases from all 100
        U.S. senators. There is no single API or clean data source for this
        information. Every senator publishes to their own website, in their own
        format, using their own content management system.
      </p>
      <p className="mt-3 text-gray-600 leading-relaxed">
        The value of this project is in the normalization. We discover each
        senator&apos;s press-release section, understand the site structure,
        extract and clean the data, and maintain a daily-updated feed that
        makes the full record searchable and analyzable.
      </p>

      {/* Current state */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Current State</h2>
        <div className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Stat
            label="Press Releases"
            value={stats.total_releases?.toLocaleString() ?? "0"}
          />
          <Stat
            label="Senators Tracked"
            value={`${stats.senators_with_releases ?? 0} / ${stats.total_senators ?? 100}`}
          />
          <Stat
            label="Date Range"
            value={`${formatDate(stats.earliest)} -- ${formatDate(stats.latest)}`}
          />
        </div>
      </section>

      {/* Methodology */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Methodology</h2>

        <h3 className="mt-6 text-lg font-medium">Three-Stage Pipeline</h3>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Data collection uses a three-stage Python pipeline. Each stage is
          independent and restartable.
        </p>

        <div className="mt-4 space-y-4">
          <Stage
            number={1}
            title="Reconnaissance"
            description="An async script probes all 100 senator websites with 21 URL
              patterns per site, fingerprints the content management system,
              extracts CSS selectors for list items, titles, dates, and detail
              links, detects the pagination mechanism, and assigns a confidence
              score. This produces a seed configuration file that tells the
              scraping scripts exactly where to find press releases and how to
              parse them."
          />
          <Stage
            number={2}
            title="Historical Backfill"
            description="A scraping script reads the seed configuration, crawls each
              senator's press release archive from January 1, 2025 to the
              present, follows pagination, visits each detail page for the full
              body text, and writes normalized records to a Postgres database.
              Deduplication happens at the database level using the source URL
              as a unique key."
          />
          <Stage
            number={3}
            title="Daily Updater"
            description="A scheduled script checks page 1 of each senator's press
              release index, compares against URLs already in the database, and
              inserts only new records. This keeps the archive current without
              re-crawling historical pages."
          />
        </div>
      </section>

      {/* CMS Families */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">
          How Senate Websites Differ
        </h2>
        <p className="mt-2 text-gray-600 leading-relaxed">
          Senate.gov provides shared infrastructure for member offices, but
          there is no standard template. Our recon discovered four distinct
          website families, each requiring its own parsing strategy.
        </p>

        <div className="mt-6 space-y-6">
          <CMSFamily
            name="Senate WordPress"
            count={familyCounts["senate-wordpress"] ?? 0}
            description="The most common template. These sites use WordPress with
              predictable DOM structures: press releases appear as post
              listings with heading links, date elements, and excerpt text.
              Pagination uses standard WordPress query parameters or
              next-page links."
            urls={["/newsroom/press-releases", "/news/press-releases", "/press-releases"]}
            selectors="List items in .element-list, titles in h2/h3 headings with links, dates in .date or time elements"
          />
          <CMSFamily
            name="Senate Custom CMS (ArticleBlock)"
            count={familyCounts["senate-generic"] ?? 0}
            description="A Senate-specific CMS component used by nearly half of all
              offices. Press releases appear as .ArticleBlock divs with a
              .ArticleTitle link and .ArticleBlock__date element. This
              pattern is consistent across all senators who use it, making
              it reliable to parse once discovered."
            urls={["/news/press-releases", "/newsroom/press-releases"]}
            selectors=".ArticleBlock container, .ArticleTitle a for links, .ArticleBlock__date for dates"
          />
          <CMSFamily
            name="Senate ColdFusion"
            count={familyCounts["senate-coldfusion"] ?? 0}
            description="A legacy CMS from the early 2000s still used by six senators.
              URLs follow the pattern /public/index.cfm/press-releases with
              UUID-based pagination parameters. The DOM structure is different
              from all other Senate sites, with table-based layouts and
              month/year filter dropdowns. Senators on ColdFusion: Fischer,
              Graham, Kennedy, Klobuchar, McConnell, Moran, Thune."
            urls={["/public/index.cfm/press-releases", "/public/index.cfm/news-releases"]}
            selectors="Table rows with UUID-based detail links, date spans in header columns"
          />
          <CMSFamily
            name="Elementor WordPress"
            count={0}
            description="A subset of WordPress sites that use the Elementor page builder.
              Press releases appear in loop containers (div.e-loop-item) with
              dynamically styled widgets for titles, dates, and excerpts. The
              HTML is more verbose than standard WordPress but the content
              structure is consistent. Some Elementor sites use different
              container patterns that required additional selector work."
            urls={["/news/press-releases/", "/media/press-releases/"]}
            selectors="div.e-loop-item containers, nested a elements for titles, .elementor-widget-post-info for dates"
          />
          <CMSFamily
            name="Senate Drupal"
            count={familyCounts["senate-drupal"] ?? 0}
            description="Only one senator (Hyde-Smith) uses Drupal. The site uses
              Drupal's Views module to display press releases with
              .views-row items and standard Drupal field markup."
            urls={["/newsroom"]}
            selectors=".views-row items, standard Drupal field classes"
          />
        </div>
      </section>

      {/* Parser family table */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Parser Family Distribution</h2>
        <table className="mt-4 w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs uppercase text-gray-500">
              <th className="pb-2 pr-4">Family</th>
              <th className="pb-2 text-right">Senators</th>
            </tr>
          </thead>
          <tbody>
            {sortedFamilies.map(([family, count]) => (
              <tr key={family} className="border-b border-gray-50">
                <td className="py-2 pr-4 font-medium">{family}</td>
                <td className="py-2 text-right tabular-nums">{count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {/* Technical challenges */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Technical Challenges</h2>

        <div className="mt-4 space-y-4 text-gray-600 leading-relaxed">
          <Challenge
            title="No standard URL patterns"
            body="Senate offices use at least 21 different URL patterns for their
              press release sections. Some use /newsroom/press-releases, others
              /news/press-releases, /media/press-releases, or entirely unique
              paths like /press/press-releases or /category/press_release/.
              One senator uses pressreleases as a single word with no hyphen.
              Our recon script probes all known patterns per site."
          />
          <Challenge
            title="ColdFusion legacy systems"
            body="Six senators still run ColdFusion, a web technology from the
              early 2000s. These sites use /public/index.cfm/ URL prefixes
              that are invisible to standard web crawling patterns. We only
              discovered them after the first recon run came back with 8
              senators unresolved, prompting manual investigation."
          />
          <Challenge
            title="Elementor DOM bloat"
            body="WordPress sites using the Elementor page builder produce HTML
              with deeply nested container divs, dynamic class names, and
              widget wrappers that make selector-based extraction unreliable.
              Our solution prioritizes content-aware selectors
              (.ArticleBlock, .ArticleTitle) over structural selectors."
          />
          <Challenge
            title="Date format inconsistency"
            body='Dates appear in at least five formats across Senate sites:
              "April 15, 2026", "Apr 15, 2026", "04/15/2026",
              "2026-04-15", and "Apr 15" (no year). The pipeline normalizes
              all formats to UTC timestamps at parse time.'
          />
          <Challenge
            title="Deduplication"
            body="The source URL serves as the natural dedup key. Each press
              release has a unique URL on the senator's website, and the
              database enforces uniqueness on this column. The daily updater
              uses ON CONFLICT DO NOTHING to skip already-archived releases
              without additional logic."
          />
        </div>
      </section>

      {/* Stack */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Technical Stack</h2>
        <div className="mt-4 space-y-2 text-sm text-gray-600">
          <StackItem label="Scraping pipeline" value="Python, httpx, BeautifulSoup, lxml" />
          <StackItem label="Database" value="Postgres (Neon) with full-text search via tsvector" />
          <StackItem label="Frontend" value="Next.js 16, React 19, Tailwind CSS 4, TypeScript" />
          <StackItem label="Hosting" value="Vercel (frontend), Neon (database)" />
          <StackItem label="Data window" value="January 1, 2025 to present, updated daily" />
        </div>
      </section>

      {/* Data sourcing */}
      <section className="mt-10 mb-8">
        <h2 className="text-xl font-semibold">Data Sourcing</h2>
        <p className="mt-2 text-gray-600 leading-relaxed">
          All data is sourced from official senator websites on senate.gov.
          Press releases are public records published by Senate offices for
          public consumption. This project collects, normalizes, and indexes
          that public information to make it searchable and analyzable. No
          private or restricted data is used.
        </p>
        <p className="mt-3 text-gray-600 leading-relaxed">
          The senator list is sourced from senate.gov&apos;s official member
          directory. Party affiliations and state assignments reflect the
          current composition of the 119th Congress.
        </p>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-gray-200 p-4">
      <p className="text-xs text-gray-500">{label}</p>
      <p className="mt-1 text-lg font-bold">{value}</p>
    </div>
  );
}

function Stage({
  number,
  title,
  description,
}: {
  number: number;
  title: string;
  description: string;
}) {
  return (
    <div className="flex gap-4">
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gray-900 text-sm font-bold text-white">
        {number}
      </div>
      <div>
        <h4 className="font-medium">{title}</h4>
        <p className="mt-1 text-sm text-gray-600 leading-relaxed">
          {description}
        </p>
      </div>
    </div>
  );
}

function CMSFamily({
  name,
  count,
  description,
  urls,
  selectors,
}: {
  name: string;
  count: number;
  description: string;
  urls: string[];
  selectors: string;
}) {
  return (
    <div className="rounded-lg border border-gray-200 p-5">
      <div className="flex items-center justify-between">
        <h4 className="font-medium">{name}</h4>
        <span className="text-sm text-gray-500">{count} senators</span>
      </div>
      <p className="mt-2 text-sm text-gray-600 leading-relaxed">
        {description}
      </p>
      <div className="mt-3 space-y-1">
        <p className="text-xs font-medium text-gray-500">Common URL patterns</p>
        <div className="flex flex-wrap gap-1">
          {urls.map((url) => (
            <code
              key={url}
              className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700"
            >
              {url}
            </code>
          ))}
        </div>
      </div>
      <div className="mt-2">
        <p className="text-xs font-medium text-gray-500">Extraction strategy</p>
        <p className="text-xs text-gray-600">{selectors}</p>
      </div>
    </div>
  );
}

function Challenge({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h4 className="font-medium text-gray-900">{title}</h4>
      <p className="mt-1 text-sm">{body}</p>
    </div>
  );
}

function StackItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="w-36 shrink-0 font-medium text-gray-900">{label}</span>
      <span>{value}</span>
    </div>
  );
}

function formatDate(d: string | null): string {
  if (!d) return "--";
  return new Date(d).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
