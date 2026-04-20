import Image from "next/image";
import { getStats, getSenators } from "../lib/queries";
import { getDataQuality, getCoverageByFamily, getCoverageDepth } from "../lib/transparency";

export const metadata = {
  title: "About — Capitol Releases",
  description:
    "Methodology, data sources and technical approach behind Capitol Releases.",
};

export const dynamic = "force-dynamic";

export default async function AboutPage() {
  const [stats, senators, quality, familyCoverage, depth] = await Promise.all([
    getStats(),
    getSenators(),
    getDataQuality(),
    getCoverageByFamily(),
    getCoverageDepth(),
  ]);

  const familyCounts: Record<string, number> = {};
  for (const s of senators) {
    const fam = s.parser_family ?? "unknown";
    familyCounts[fam] = (familyCounts[fam] ?? 0) + 1;
  }
  const sortedFamilies = Object.entries(familyCounts).sort(
    (a, b) => b[1] - a[1]
  );

  const depthRows = depth as {
    full_name: string;
    party: string;
    state: string;
    parser_family: string;
    total: number;
    dated: number;
    earliest: string | null;
    latest: string | null;
    coverage: string;
  }[];

  const complete = depthRows.filter((d) => d.coverage === "complete").length;
  const partial = depthRows.filter((d) => d.coverage === "partial").length;
  const undated = depthRows.filter((d) => d.coverage === "undated").length;
  const empty = depthRows.filter((d) => d.coverage === "empty").length;

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-3xl font-bold">About Capitol Releases</h1>
      <p className="mt-3 text-stone-600 leading-relaxed">
        Capitol Releases is a journalism and public-records project that builds
        a normalized, searchable archive of official press releases from all 100
        U.S. senators. There is no single API or clean data source for this
        information. Every senator publishes to their own website, in their own
        format, using their own content management system.
      </p>

      {/* About the developer */}
      <section className="mt-10">
        <h2 className="font-serif text-2xl">About the developer</h2>
        <div className="mt-4 flex items-start gap-5">
          <Image
            src="/trevor-brown.jpeg"
            alt="Trevor Brown"
            width={96}
            height={96}
            className="rounded-full shrink-0 object-cover"
          />
          <p className="text-stone-600 leading-relaxed">
            Built by{" "}
            <a href="https://trevorthewebdeveloper.com" className="underline text-stone-900 hover:text-stone-600 transition-colors">
              Trevor Brown
            </a>
            , investigative data journalist turned web developer. 15 years
            of political reporting, most recently six years covering elections,
            dark money, financial disclosures and government accountability at{" "}
            <a href="https://oklahomawatch.org" className="underline text-stone-900 hover:text-stone-600 transition-colors">
              Oklahoma Watch
            </a>
            . This project bridges both worlds — journalism instinct driving
            a developer tool.
          </p>
        </div>
      </section>

      <hr className="my-8 border-stone-200" />

      {/* Data quality - upfront honesty */}
      <section className="mt-10 rounded-lg border border-amber-200 bg-amber-50 p-5">
        <h2 className="text-xl font-semibold text-amber-900">
          Data Quality Report
        </h2>
        <p className="mt-2 text-sm text-amber-800 leading-relaxed">
          This project is transparent about what it has and what it is missing.
          These numbers update live from the database.
        </p>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <QualityStat label="Total Releases" value={quality.total} />
          <QualityStat
            label="With Dates"
            value={quality.has_date}
            pct={Math.round((quality.has_date / quality.total) * 100)}
          />
          <QualityStat
            label="With Body Text"
            value={quality.has_body}
            pct={Math.round((quality.has_body / quality.total) * 100)}
          />
          <QualityStat
            label="Senators"
            value={`${quality.senators_with_data}/100`}
          />
        </div>

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          <QualityStat
            label="Complete (to Jan 2025)"
            value={complete}
            color="green"
          />
          <QualityStat label="Partial Coverage" value={partial} color="amber" />
          <QualityStat
            label="Undated (have data)"
            value={undated}
            color="amber"
          />
          <QualityStat label="Empty" value={empty} color="red" />
        </div>

        <div className="mt-4 text-xs text-amber-700 leading-relaxed">
          <p>
            <strong>Known issues:</strong> {quality.null_date.toLocaleString()}{" "}
            records ({Math.round((quality.null_date / quality.total) * 100)}%)
            are missing publication dates. This primarily affects ColdFusion and
            some custom CMS sites where the date is embedded in the page text
            rather than in a structured HTML element. {partial} senators have
            data that does not reach back to January 2025 due to pagination
            limitations on their specific site structure.
          </p>
        </div>
      </section>

      {/* Per-senator coverage table */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">
          Coverage by Senator
        </h2>
        <p className="mt-2 text-sm text-stone-500">
          Every senator&apos;s scraping status, release count, date range and
          CMS type. This is the ground truth of what we have and what we are
          missing.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b text-left uppercase text-stone-400">
                <th className="pb-2 pr-3">Senator</th>
                <th className="pb-2 pr-3">State</th>
                <th className="pb-2 pr-3 text-right">Releases</th>
                <th className="pb-2 pr-3 text-right">Dated</th>
                <th className="pb-2 pr-3">Earliest</th>
                <th className="pb-2 pr-3">CMS</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {depthRows.map((d) => (
                <tr
                  key={d.full_name}
                  className="border-b border-stone-50 hover:bg-stone-50"
                >
                  <td className="py-1.5 pr-3 font-medium">{d.full_name}</td>
                  <td className="py-1.5 pr-3">
                    {d.party}-{d.state}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">
                    {d.total}
                  </td>
                  <td className="py-1.5 pr-3 text-right tabular-nums">
                    {d.dated}
                  </td>
                  <td className="py-1.5 pr-3 tabular-nums">
                    {d.earliest ?? "—"}
                  </td>
                  <td className="py-1.5 pr-3 text-stone-400">
                    {d.parser_family?.replace("senate-", "") ?? "?"}
                  </td>
                  <td className="py-1.5">
                    <CoverageStatus status={d.coverage} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Coverage by CMS family */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Coverage by CMS Family</h2>
        <p className="mt-2 text-sm text-stone-500">
          How well each website type is being scraped. Date parsing accuracy
          varies significantly by CMS.
        </p>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-stone-400">
                <th className="pb-2 pr-4">CMS Family</th>
                <th className="pb-2 pr-4 text-right">Senators</th>
                <th className="pb-2 pr-4 text-right">Releases</th>
                <th className="pb-2 pr-4 text-right">Dated</th>
                <th className="pb-2 pr-4 text-right">Undated</th>
                <th className="pb-2 text-right">Date Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {(
                familyCoverage as {
                  parser_family: string;
                  senator_count: number;
                  release_count: number;
                  dated: number;
                  undated: number;
                  has_body: number;
                }[]
              ).map((f) => (
                <tr
                  key={f.parser_family}
                  className="border-b border-stone-50"
                >
                  <td className="py-2 pr-4 font-medium">
                    {f.parser_family ?? "unknown"}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {f.senator_count.toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {f.release_count.toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {f.dated.toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-right tabular-nums">
                    {f.undated.toLocaleString()}
                  </td>
                  <td className="py-2 text-right tabular-nums">
                    {f.release_count > 0
                      ? `${Math.round((f.dated / f.release_count) * 100)}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Methodology */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Methodology</h2>

        <h3 className="mt-6 text-lg font-medium">Three-Stage Pipeline</h3>
        <p className="mt-2 text-stone-600 leading-relaxed">
          Data collection uses a three-stage Python pipeline. Each stage is
          independent and restartable.
        </p>

        <div className="mt-4 space-y-4">
          <Stage
            number={1}
            title="Reconnaissance"
            description="An async script probes all 100 senator websites with 21 URL
              patterns per site, fingerprints the content management system,
              extracts CSS selectors for list items, titles, dates and detail
              links, detects the pagination mechanism and assigns a confidence
              score. This produces a seed configuration file that tells the
              scraping scripts exactly where to find press releases and how to
              parse them. The script was run iteratively — the first pass
              discovered 92 senators, then ColdFusion paths were added for 6
              more, then individual URLs were manually corrected for the final 2.
              The House required a separate run with conservative rate limiting
              (3 concurrent, 1.5s delay) to avoid the house.gov WAF."
          />
          <Stage
            number={2}
            title="Historical Backfill"
            description="A scraping script reads the seed configuration, crawls each
              senator's press release archive from January 1, 2025 to the
              present, follows pagination, visits each detail page for the full
              body text and writes normalized records to a Postgres database.
              Deduplication happens at the database level using the source URL
              as a unique key. The backfill was run multiple times as pagination
              bugs were discovered and fixed. Each run skips already-scraped
              URLs and only inserts new records."
          />
          <Stage
            number={3}
            title="Daily Updater"
            description="A collector-based updater checks each senator via their
              assigned collection method (HTTP scraping for 70 senators, Playwright
              for 19, RSS feeds for 11). It fetches page 1, deduplicates
              against known URLs and inserts only new records. Runs in under
              2 minutes for all 100 senators. Includes post-run anomaly detection
              and email alerts for failures."
          />
        </div>
      </section>

      {/* How each CMS was discovered and handled */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">
          How Each CMS Type Was Discovered
        </h2>
        <p className="mt-2 text-stone-600 leading-relaxed">
          Senate websites use at least eight distinct content management systems.
          Each required its own discovery process, selector strategy and
          pagination handling. Here is exactly how each was identified and
          what we had to build to scrape it.
        </p>

        <div className="mt-6 space-y-6">
          <CMSDiscovery
            name="Senate WordPress (48 senators)"
            discovery="Identified by meta generator tags containing 'WordPress' or
              wp-content in stylesheet URLs. The most common Senate CMS."
            selectors="List items matched by standard WordPress post selectors (article,
              .element-list .element). Titles in h2/h3 heading links. Dates in
              time elements or .date spans."
            pagination="Standard WordPress ?page=N or /page/N/ URL patterns. Also
              supports a[rel='next'] links."
            challenges="Some WordPress sites use the Elementor page builder, which wraps
              content in deeply nested div containers with dynamic class names.
              These required specific e-loop-item selectors rather than standard
              WordPress post selectors."
          />
          <CMSDiscovery
            name="Senate ArticleBlock / Custom CMS (47 senators)"
            discovery="Identified by the presence of .ArticleBlock elements in the DOM.
              This is a Senate-specific CMS component not used outside senate.gov.
              We only discovered it after the first backfill run produced 0
              results for ~30 senators whose pages had content visible in the
              browser. Manual DOM inspection revealed the .ArticleBlock pattern."
            selectors=".ArticleBlock as the container, .ArticleTitle a for the title link,
              .ArticleBlock__date for the publication date."
            pagination="Uses numbered page links in a .pagination container with a
              'Showing page 1 2 3...' pattern. The current page is marked with
              a non-link element. We find the current page number and look for
              the next number's link."
            challenges="The ArticleBlock sites also have ?pagenum_rs= pagination parameters
              that our initial pagination code missed entirely. The 'Next' link
              text had to be matched explicitly."
          />
          <CMSDiscovery
            name="Senate ColdFusion (7 senators)"
            discovery="Discovered after the first recon run returned 8 senators as
              'not found'. A manual investigation revealed 7 used ColdFusion --
              a legacy web technology from the early 2000s. URLs follow the
              pattern /public/index.cfm/press-releases, which is invisible to
              standard URL probing. Senators: Durbin, Fischer, Graham, Kennedy,
              Klobuchar, McConnell, Moran."
            selectors="Table rows with UUID-based detail links. Dates in table header
              cells. The DOM structure is completely different from all other
              Senate sites."
            pagination="UUID-based offset parameters. Pagination links contain
              ?startPosition=N or similar parameters. The total page count is
              visible in pagination metadata."
            challenges="ColdFusion sites return 403 to some User-Agent strings. Date
              extraction was the biggest challenge — dates are embedded in
              page text rather than structured HTML elements, leading to high
              null-date rates."
          />
          <CMSDiscovery
            name="Elementor Loop Items (Banks, McCormick, etc.)"
            discovery="A subset of WordPress sites using the Elementor page builder
              with JetEngine or native loop widgets. Identified by
              div.e-loop-item class patterns in the DOM."
            selectors="div.e-loop-item as the container. Title extracted from the first
              substantial a[href] link containing senate.gov. Date from
              .elementor-widget-post-info."
            pagination="Most use standard WordPress pagination. Some use AJAX-based
              load-more (not yet supported)."
            challenges="The recon script initially stored span.elementor-grid-item as the
              list selector — these are actually pagination dots, not press
              release items. This caused the backfill to find 'items' but
              extract no titles. Fixed by prioritizing e-loop-item over the
              stored recon selector."
          />
          <CMSDiscovery
            name="PressBlock (Grassley)"
            discovery="Unique to Senator Grassley's website. Found by manual browser
              inspection after the URL /news/press-releases returned 404.
              The real path is /news/news-releases."
            selectors=".PressBlock container, links in .PressBlock__content, dates parsed
              from text within the block."
            pagination="Standard numbered pagination in .pagination container."
            challenges="Grassley's site 404s on the 'press-releases' path that works for
              most senators. Had to discover the 'news-releases' variant manually."
          />
          <CMSDiscovery
            name="Media List (Wicker)"
            discovery="Unique to Senator Wicker. A custom CMS that also uses div.element
              wrappers (like Rick Scott's pattern) but with a different internal
              structure. Discovered when Wicker showed 0 results despite having
              content."
            selectors="div.media-list-body as the container. Title from
              .post-media-list-title (not from the link text, which was empty).
              Date from .post-media-list-date."
            pagination="Standard ?page=N query parameter."
            challenges="Two competing selectors: div.element (matched first, found Rick
              Scott-style items) and div.media-list-body (the correct one).
              Had to reorder selector priority. The title was in a separate div
              rather than in the link text, which broke the generic extraction."
          />
          <CMSDiscovery
            name="WordPress Divi (Bennet)"
            discovery="Senator Bennet uses WordPress with the Divi theme. The original
              URL pointed to a single 2014 post. The real press release listing
              is at /news/."
            selectors="article.et_pb_post containers. Title in h3.entry-title a.
              Date in span.published."
            pagination="WordPress /page/N/ pattern with ?et_blog query parameter."
            challenges="The recon-detected URL was completely wrong (a single old post
              rather than the listing). Required manual URL correction."
          />
          <CMSDiscovery
            name="WordPress postItem (Welch)"
            discovery="Senator Welch uses a custom WordPress template with Tailwind CSS
              classes. Press releases are at /category/press-release/."
            selectors="article.postItem containers. Title from substantial a[href] links.
              Date from .postDate span."
            pagination="Standard WordPress /page/N/."
            challenges="The /news/ page mixes press releases with other post types.
              The /category/press-release/ path filters to only press releases
              but was not in the standard probe list."
          />
          <CMSDiscovery
            name="Senate Drupal (1 senator, 254 House members)"
            discovery="Identified by Drupal CSS classes and .views-row patterns. Only
              one senator (Hyde-Smith) uses Drupal, but it is the dominant CMS
              for the U.S. House (254 of 437 members)."
            selectors=".views-row items with standard Drupal field markup."
            pagination="Drupal pager with ?page=N parameters."
            challenges="Minimal — Drupal sites are the most consistent and reliable to
              scrape. The House's standardization on Drupal makes it significantly
              easier to scrape at scale than the Senate."
          />
        </div>
      </section>

      {/* Technical challenges */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Challenges and Failures</h2>
        <p className="mt-2 text-stone-600 leading-relaxed">
          This section documents things that went wrong and how they were fixed.
          Transparency about failures is as important as documenting successes.
        </p>

        <div className="mt-4 space-y-4 text-stone-600 leading-relaxed">
          <Challenge
            title="Null publication dates — once endemic, now under 0.5%"
            body={`${quality.null_date.toLocaleString()} out of ${quality.total.toLocaleString()}
              press releases are still missing dates. The early backfill left
              over half the corpus undated because the date parser didn't
              understand ArticleBlock or ColdFusion date placement. Both CMS
              families embed dates as bare text next to the title rather than
              in a structured element. A dedicated find_all_previous() walk for
              h2.title elements and five additional date-format regexes cut
              the rate from roughly 50 percent to under one half of one percent.
              The remaining nulls are real edge cases — historical items where
              the date is in an image or was never published.`}
          />
          <Challenge
            title="Pagination broke silently for 65 senators"
            body="The initial backfill only scraped page 1 for most senators
              because the pagination detection code didn't match Senate-specific
              patterns (?pagenum_rs=, numbered page lists with no 'next' button,
              WordPress ?et_blog parameters). This wasn't discovered until a
              verification script was built to compare DB counts against live
              site totals. The fix required three rounds of pagination code
              rewrites."
          />
          <Challenge
            title="House.gov WAF blocks automated access"
            body="House member websites sit behind a web application firewall that
              returns 403 for requests missing Accept/Accept-Language headers.
              Even with proper headers, the WAF blocks after a burst of
              requests from the same IP. The House recon required concurrency
              of 3 (vs 12 for Senate) and 1.5-second delays between requests.
              The first run got 45 members; the second (conservative) run
              got 411; manual investigation found the remaining 26."
          />
          <Challenge
            title="Neon connection timeouts during long backfills"
            body="The initial backfill used a single shared database connection
              for all 100 senators. During long runs (50 pages per senator),
              Neon's connection pooler timed out. Fixed by opening a fresh
              database connection per senator."
          />
          <Challenge
            title="ColdFusion sites invisible to standard URL probing"
            body="6 senators use ColdFusion with /public/index.cfm/ URL prefixes.
              These paths are not discoverable by probing standard patterns like
              /newsroom/press-releases. Only found after manual investigation
              of the 8 senators that the recon script failed to discover."
          />
          <Challenge
            title="Recon stored bad selectors that sabotaged the backfill"
            body="The automated recon stored span.elementor-grid-item as the
              list-item selector for several Elementor sites. These are
              pagination dots, not press releases. The backfill would find
              'items' but extract no titles, silently producing 0 results.
              Fixed by blacklisting known-bad selectors and prioritizing
              content-aware selectors (.ArticleBlock, .e-loop-item) over
              stored recon data."
          />
          <Challenge
            title="Accent characters in names corrupted member IDs"
            body="The ID generation function stripped non-ASCII characters,
              producing IDs like 'snchez-linda' for Linda Sanchez and
              'velzquez-nydia' for Nydia Velazquez. This caused the seed
              file updates to miss 4 House members. Fixed by matching
              against the mangled IDs directly."
          />
        </div>
      </section>

      {/* Stack */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Technical Stack</h2>
        <div className="mt-4 space-y-2 text-sm text-stone-600">
          <StackItem
            label="Scraping pipeline"
            value="Python 3.14, httpx (async HTTP), BeautifulSoup + lxml (HTML parsing)"
          />
          <StackItem
            label="Database"
            value="Postgres (Neon) with tsvector full-text search, JSONB metadata"
          />
          <StackItem
            label="Frontend"
            value="Next.js 16, React 19, Tailwind CSS 4, TypeScript, D3.js"
          />
          <StackItem label="Hosting" value="Vercel (frontend), Neon (database)" />
          <StackItem
            label="Source code"
            value="github.com/tbrown034/capitol-releases"
          />
          <StackItem
            label="Data window"
            value="January 1, 2025 to present"
          />
        </div>
      </section>

      {/* Data sourcing */}
      <section className="mt-10">
        <h2 className="text-xl font-semibold">Data Sourcing</h2>
        <p className="mt-2 text-stone-600 leading-relaxed">
          All data is sourced from official senator websites on senate.gov.
          Press releases are public records published by Senate offices for
          public consumption. This project collects, normalizes and indexes
          that public information to make it searchable and analyzable. No
          private or restricted data is used.
        </p>
        <p className="mt-3 text-stone-600 leading-relaxed">
          The senator list is sourced from senate.gov&apos;s official member
          directory. Party affiliations and state assignments reflect the
          current composition of the 119th Congress. The House member list
          (437 members) was sourced from congress.gov API and the
          unitedstates/congress-legislators GitHub repository.
        </p>
        <p className="mt-3 text-stone-600 leading-relaxed">
          This project scrapes public web pages at a polite rate (1 concurrent
          request per domain, 0.5-1.5 second delays). No login credentials,
          CAPTCHA circumvention or rate-limit evasion is used. All requests
          identify themselves with standard browser headers.
        </p>
      </section>

      <hr className="my-8 border-stone-200" />

      {/* Related resources */}
      <section className="mt-10">
        <h2 className="font-serif text-2xl">Related resources</h2>
        <div className="mt-4 space-y-3 text-stone-600">
          <ResourceLink
            href="https://www.senate.gov/senators/"
            title="U.S. Senate Member Directory"
            description="Official list of all current senators."
          />
          <ResourceLink
            href="https://www.congress.gov/"
            title="Congress.gov"
            description="Official source for legislation, floor activity and committee records."
          />
          <ResourceLink
            href="https://www.propublica.org/datastore/api/propublica-congress-api"
            title="ProPublica Congress API"
            description="Structured data on bills, votes and member information."
          />
          <ResourceLink
            href="https://github.com/unitedstates/congress-legislators"
            title="unitedstates/congress-legislators"
            description="Open data on every member of Congress, past and present."
          />
        </div>
      </section>

      <hr className="my-8 border-stone-200" />

      {/* Open source */}
      <section className="mt-10">
        <h2 className="font-serif text-2xl">Open source</h2>
        <p className="mt-3 text-stone-600 leading-relaxed">
          Capitol Releases is open source. The code, data pipeline and
          documentation are available on{" "}
          <a href="https://github.com/tbrown034/capitol-releases" className="underline text-stone-900 hover:text-stone-600 transition-colors">
            GitHub
          </a>
          . Found a bug or data error?{" "}
          <a href="https://github.com/tbrown034/capitol-releases/issues" className="underline text-stone-900 hover:text-stone-600 transition-colors">
            Open an issue
          </a>{" "}
          or email{" "}
          <a href="mailto:trevorbrown.web@gmail.com" className="underline text-stone-900 hover:text-stone-600 transition-colors">
            trevorbrown.web@gmail.com
          </a>
          .
        </p>
      </section>

      <div className="h-12" />
    </div>
  );
}

function QualityStat({
  label,
  value,
  pct,
  color = "stone",
}: {
  label: string;
  value: number | string;
  pct?: number;
  color?: "stone" | "green" | "amber" | "red";
}) {
  const colors = {
    stone: "border-stone-200 bg-white",
    green: "border-green-200 bg-green-50",
    amber: "border-amber-200 bg-amber-50",
    red: "border-red-200 bg-red-50",
  };
  return (
    <div className={`rounded-lg border p-3 ${colors[color]}`}>
      <p className="text-xs text-stone-500">{label}</p>
      <p className="mt-0.5 text-lg font-bold tabular-nums">
        {typeof value === "number" ? value.toLocaleString() : value}
        {pct !== undefined && (
          <span className="ml-1 text-xs font-normal text-stone-400">
            ({pct}%)
          </span>
        )}
      </p>
    </div>
  );
}

function CoverageStatus({ status }: { status: string }) {
  const styles = {
    complete: "bg-green-100 text-green-800",
    partial: "bg-amber-100 text-amber-800",
    undated: "bg-blue-100 text-blue-800",
    empty: "bg-red-100 text-red-800",
  } as Record<string, string>;
  return (
    <span
      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${styles[status] ?? "bg-stone-100 text-stone-600"}`}
    >
      {status}
    </span>
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
      <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-stone-900 text-sm font-bold text-white">
        {number}
      </div>
      <div>
        <h4 className="font-medium">{title}</h4>
        <p className="mt-1 text-sm text-stone-600 leading-relaxed">
          {description}
        </p>
      </div>
    </div>
  );
}

function CMSDiscovery({
  name,
  discovery,
  selectors,
  pagination,
  challenges,
}: {
  name: string;
  discovery: string;
  selectors: string;
  pagination: string;
  challenges: string;
}) {
  return (
    <div className="rounded-lg border border-stone-200 bg-white p-5">
      <h4 className="font-medium">{name}</h4>
      <div className="mt-3 space-y-2 text-sm text-stone-600 leading-relaxed">
        <div>
          <span className="font-medium text-stone-800">How discovered:</span>{" "}
          {discovery}
        </div>
        <div>
          <span className="font-medium text-stone-800">Selectors:</span>{" "}
          {selectors}
        </div>
        <div>
          <span className="font-medium text-stone-800">Pagination:</span>{" "}
          {pagination}
        </div>
        <div>
          <span className="font-medium text-stone-800">Challenges:</span>{" "}
          {challenges}
        </div>
      </div>
    </div>
  );
}

function Challenge({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h4 className="font-medium text-stone-900">{title}</h4>
      <p className="mt-1 text-sm">{body}</p>
    </div>
  );
}

function ResourceLink({ href, title, description }: { href: string; title: string; description: string }) {
  return (
    <div>
      <a href={href} className="underline font-medium text-stone-900 hover:text-stone-600 transition-colors" target="_blank" rel="noopener noreferrer">
        {title}
      </a>
      <span className="text-stone-400"> —</span>
      <span>{description}</span>
    </div>
  );
}

function StackItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-3">
      <span className="w-36 shrink-0 font-medium text-stone-900">{label}</span>
      <span>{value}</span>
    </div>
  );
}
