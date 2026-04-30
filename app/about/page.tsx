import Image from "next/image";
import { getSenators } from "../lib/queries";
import {
  getDataQuality,
  getCoverageByFamily,
  getCoverageDepth,
  getCollectionMethodBreakdown,
  getContentTypeBreakdown,
  getDeletionCount,
} from "../lib/transparency";

export const metadata = {
  title: "Methodology — Capitol Releases",
  description:
    "How Capitol Releases collects, classifies and archives every U.S. senator's official press releases.",
};

// About page is mostly static + per-senator coverage table from a daily-cron
// query. Long ISR is fine and saves a 2.5s SSR pass per visitor.
export const revalidate = 3600;

const CONTENT_TYPE_LABELS: Record<string, string> = {
  press_release: "Press release",
  statement: "Statement",
  op_ed: "Op-ed",
  floor_statement: "Floor statement",
  photo_release: "Photo release",
  letter: "Letter",
  blog: "Blog",
  other: "Other",
};

export default async function AboutPage() {
  const [senators, quality, familyCoverage, depth, collectionMethods, contentTypes, deletionCount] =
    await Promise.all([
      getSenators(),
      getDataQuality(),
      getCoverageByFamily(),
      getCoverageDepth(),
      getCollectionMethodBreakdown(),
      getContentTypeBreakdown(),
      getDeletionCount(),
    ]);

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

  const methodRows = collectionMethods as {
    collection_method: string;
    senator_count: number;
  }[];
  const methodCounts: Record<string, number> = {};
  for (const row of methodRows) methodCounts[row.collection_method] = row.senator_count;

  const typeRows = contentTypes as { content_type: string; count: number }[];
  const totalTyped = typeRows.reduce((acc, r) => acc + r.count, 0);

  const datePct = Math.round((quality.has_date / quality.total) * 100);
  const bodyPct = Math.round((quality.has_body / quality.total) * 100);

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Methodology
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-2">
        Capitol Releases is a public-records project. There is no single API
        or clean data source for senator press releases &mdash; every office
        publishes to its own site in its own format. This page documents how
        the archive is built, where the data comes from and what is missing.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed max-w-2xl mb-10">
        All counts on this page update live from the database.
      </p>

      {/* Developer bio */}
      <section className="mb-12 flex items-start gap-5">
        <Image
          src="/trevor-brown.jpeg"
          alt="Trevor Brown"
          width={72}
          height={72}
          className="shrink-0 object-cover"
        />
        <p className="text-sm text-neutral-600 leading-relaxed">
          Built by{" "}
          <a
            href="https://trevorthewebdeveloper.com"
            className="underline underline-offset-2 text-neutral-900 hover:text-neutral-600 transition-colors"
          >
            Trevor Brown
          </a>
          , investigative data journalist turned web developer. Fifteen years
          of political reporting &mdash; most recently six covering elections,
          dark money, financial disclosures and government accountability at{" "}
          <a
            href="https://oklahomawatch.org"
            className="underline underline-offset-2 text-neutral-900 hover:text-neutral-600 transition-colors"
          >
            Oklahoma Watch
          </a>
          . This project bridges both worlds &mdash; a journalist&apos;s
          instinct driving a developer&apos;s tool.
        </p>
      </section>

      {/* Data quality */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          Data quality
        </h2>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-neutral-200 border border-neutral-200">
          <Stat label="Total releases" value={quality.total.toLocaleString()} />
          <Stat
            label="With dates"
            value={`${quality.has_date.toLocaleString()}`}
            suffix={`${datePct}%`}
          />
          <Stat
            label="With body text"
            value={`${quality.has_body.toLocaleString()}`}
            suffix={`${bodyPct}%`}
          />
          <Stat label="Senators with data" value={`${quality.senators_with_data}/100`} />
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-neutral-200 border-x border-b border-neutral-200">
          <Stat label="Complete to Jan 2025" value={complete} />
          <Stat label="Partial coverage" value={partial} />
          <Stat label="Undated only" value={undated} />
          <Stat label="Empty" value={empty} />
        </div>

        <p className="text-xs text-neutral-500 leading-relaxed mt-4 max-w-2xl">
          Known issues: {quality.null_date.toLocaleString()}{" "}records
          ({Math.round((quality.null_date / quality.total) * 100)}%) are
          missing publication dates &mdash; primarily ColdFusion and custom
          sites that embed dates in page text rather than structured markup.
          {" "}{partial}{" "}senators have archives that do not reach back to
          January 2025 due to pagination limits on their specific CMS.
          {deletionCount > 0 && (
            <>
              {" "}We periodically re-fetch source URLs as a data-quality
              check. {" "}
              <span className="text-neutral-900 font-medium">
                {deletionCount.toLocaleString()}
              </span>{" "}
              source URL{deletionCount !== 1 ? "s have" : " has"}{" "}stopped
              resolving on multiple consecutive checks; the captured text
              remains in the archive. We don&apos;t treat this as proof of
              intentional removal &mdash; sites get redesigned, URLs
              restructure, CDNs hiccup &mdash; just an integrity signal worth
              recording.
            </>
          )}
        </p>
      </section>

      {/* What we classify */}
      {totalTyped > 0 && (
        <section className="mb-12">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
            What we classify
          </h2>
          <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-4">
            Every item is tagged with a content type at ingest. The default
            feed surfaces press releases; other types are classified, stored
            and queryable. Third-party clippings and &ldquo;in the news&rdquo;
            aggregations are not collected.
          </p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-neutral-200 border border-neutral-200">
            {typeRows.map((t) => (
              <Stat
                key={t.content_type}
                label={CONTENT_TYPE_LABELS[t.content_type] ?? t.content_type}
                value={t.count.toLocaleString()}
                suffix={`${Math.round((t.count / totalTyped) * 100)}%`}
              />
            ))}
          </div>
        </section>
      )}

      {/* How we collect */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          How we collect
        </h2>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-6">
          Collection runs in three stages. Each is independent and restartable.
        </p>

        <div className="space-y-5">
          <Stage
            number={1}
            title="Reconnaissance"
            description="An async script probes each senator's site with 21 URL
              patterns, fingerprints the CMS, extracts CSS selectors for list
              items, titles, dates and detail links, and assigns a confidence
              score. Output is a seed configuration used by every downstream
              stage."
          />
          <Stage
            number={2}
            title="Historical backfill"
            description="A one-time deep crawl that reads the seed config,
              follows each senator's archive from January 1, 2025 to today,
              visits each detail page for body text and writes normalized
              records to Postgres. Deduplication happens on source URL."
          />
          <Stage
            number={3}
            title="Daily updater"
            description={`Runs every senator through their assigned
              collection method &mdash; httpx for ${methodCounts.httpx ?? 0},
              Playwright for ${methodCounts.playwright ?? 0}, RSS for
              ${methodCounts.rss ?? 0}${methodCounts.whitehouse ? `, plus a dedicated White House collector` : ""}.
              It fetches page one, dedupes against known URLs, and inserts
              only new records. Post-run anomaly detection flags missing
              senators, date-parse spikes and coverage gaps.`}
          />
        </div>
      </section>

      {/* CMS landscape */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          The CMS landscape
        </h2>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-4">
          Senate sites use at least eight distinct content management systems.
          Each required its own selectors and pagination handling. The major
          families:
        </p>
        <ul className="text-sm text-neutral-600 leading-relaxed max-w-2xl space-y-2 list-disc pl-5">
          <li>
            <strong className="text-neutral-900">Senate WordPress</strong>{" "}
            &mdash; the most common CMS. Standard post selectors; most expose
            a <code className="font-[family-name:var(--font-dm-mono)] text-xs text-neutral-500">wp-json/wp/v2/posts</code> JSON endpoint we can hit directly.
          </li>
          <li>
            <strong className="text-neutral-900">ArticleBlock</strong> &mdash;
            a Senate-specific custom CMS. Identified by{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-xs text-neutral-500">.ArticleBlock</code> DOM elements.
          </li>
          <li>
            <strong className="text-neutral-900">ColdFusion</strong> &mdash;
            legacy tech on a handful of sites (Durbin, Fischer, Graham, Kennedy,
            Klobuchar, McConnell, Moran). Dates are embedded in text rather
            than structured markup, which accounts for most of the null-date
            rate.
          </li>
          <li>
            <strong className="text-neutral-900">Elementor / Divi</strong>{" "}
            &mdash; WordPress page-builder variants. Sometimes use AJAX
            pagination that requires Playwright.
          </li>
          <li>
            <strong className="text-neutral-900">Drupal</strong> &mdash; one
            senator (Hyde-Smith), but the dominant CMS in the House.
            Predictable markup, easy to scrape at scale.
          </li>
        </ul>
      </section>

      {/* Coverage by CMS */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          Coverage by CMS
        </h2>
        <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
          Date-parsing accuracy varies significantly by CMS. ColdFusion and
          generic sites lag; structured WordPress and Drupal are near-100%.
        </p>
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
                <th className="pb-2 pr-4 text-left font-medium">Family</th>
                <th className="pb-2 pr-4 text-right font-medium">Senators</th>
                <th className="pb-2 pr-4 text-right font-medium">Releases</th>
                <th className="pb-2 pr-4 text-right font-medium">Dated</th>
                <th className="pb-2 pr-4 text-right font-medium">Undated</th>
                <th className="pb-2 text-right font-medium">Date accuracy</th>
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
              ).map((f, i) => (
                <tr
                  key={f.parser_family}
                  className={`border-b border-neutral-100 ${i % 2 === 1 ? "bg-neutral-50/60" : ""}`}
                >
                  <td className="py-2 pr-4 text-neutral-900">
                    {f.parser_family?.replace("senate-", "") ?? "unknown"}
                  </td>
                  <td className="py-2 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500">
                    {f.senator_count.toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-600">
                    {f.release_count.toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500">
                    {f.dated.toLocaleString()}
                  </td>
                  <td className="py-2 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500">
                    {f.undated.toLocaleString()}
                  </td>
                  <td className="py-2 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-700">
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

      {/* Coverage by senator */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          Coverage by senator
        </h2>
        <p className="text-xs text-neutral-500 leading-relaxed mb-4 max-w-2xl">
          The ground truth of what we have. Every senator, their release
          count, date range and CMS type.
        </p>
        <div className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
          <table className="w-full min-w-[720px] text-xs">
            <thead>
              <tr className="border-b border-neutral-800 text-[11px] uppercase tracking-wider text-neutral-500">
                <th className="pb-2 pr-3 text-left font-medium">Senator</th>
                <th className="pb-2 pr-3 text-left font-medium">State</th>
                <th className="pb-2 pr-3 text-right font-medium">Releases</th>
                <th className="pb-2 pr-3 text-right font-medium">Dated</th>
                <th className="pb-2 pr-3 text-left font-medium">Earliest</th>
                <th className="pb-2 pr-3 text-left font-medium">CMS</th>
                <th className="pb-2 text-left font-medium">Status</th>
              </tr>
            </thead>
            <tbody>
              {depthRows.map((d, i) => (
                <tr
                  key={d.full_name}
                  className={`border-b border-neutral-100 ${i % 2 === 1 ? "bg-neutral-50/60" : ""}`}
                >
                  <td className="py-1.5 pr-3 text-neutral-900">
                    {d.full_name}
                  </td>
                  <td className="py-1.5 pr-3 text-neutral-500">
                    {d.party}-{d.state}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-700">
                    {d.total.toLocaleString()}
                  </td>
                  <td className="py-1.5 pr-3 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500">
                    {d.dated.toLocaleString()}
                  </td>
                  <td className="py-1.5 pr-3 font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500">
                    {d.earliest ?? "—"}
                  </td>
                  <td className="py-1.5 pr-3 text-neutral-500">
                    {d.parser_family?.replace("senate-", "") ?? "?"}
                  </td>
                  <td className="py-1.5">
                    <CoverageBadge status={d.coverage} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Known limits */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          Known limits
        </h2>
        <ul className="text-sm text-neutral-600 leading-relaxed max-w-2xl space-y-3 list-disc pl-5">
          <li>
            <strong className="text-neutral-900">Null dates.</strong> About{" "}
            {Math.round((quality.null_date / quality.total) * 100)}% of records
            still lack structured dates. Primarily ColdFusion and custom sites
            where dates live in page text.
          </li>
          <li>
            <strong className="text-neutral-900">Truncated archives.</strong>{" "}
            Some senator sites cap historical pagination below our January 2025
            window. We flag these in the per-senator table as{" "}
            <span className="font-[family-name:var(--font-dm-mono)] text-xs text-neutral-700">partial</span>.
          </li>
          <li>
            <strong className="text-neutral-900">Seats that changed hands.</strong>{" "}
            Where a senator left office during the window (Rubio to Moody,
            Vance to Husted), we collect only the current holder&apos;s
            releases from their start date. Predecessor content is out of
            scope.
          </li>
          <li>
            <strong className="text-neutral-900">Armstrong exception.</strong>{" "}
            Sen. Armstrong (R-OK) has published zero releases since taking
            office. His row stays configured and health-checked; coverage is
            expected to stay at zero until his office begins publishing.
          </li>
          <li>
            <strong className="text-neutral-900">House expansion pending.</strong>{" "}
            All 437 House members are discovered and seed-configured. Scraping
            is a planned phase &mdash; Drupal dominates there, which should
            make House at-scale collection easier than Senate.
          </li>
        </ul>
      </section>

      {/* Data sourcing */}
      {/* State expansion — TX is the first non-federal corpus. */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          State expansion
        </h2>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-3">
          The same collection method extends to the{" "}
          <a
            href="/texas"
            className="underline underline-offset-2 text-neutral-900 hover:text-neutral-600 transition-colors"
          >
            Texas State Senate
          </a>
          : 31 districts, daily-updated archive of every member&apos;s
          pressroom on senate.texas.gov, scoped to January 2025 forward.
        </p>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-3">
          State legislatures publish on a fundamentally different cadence
          than Congress &mdash; output spikes during session and falls off
          in the interim, and many state senators don&apos;t publish online
          at all. The TX directory makes that visible: 18 of 30 publish; the
          other 12 maintain pressrooms but rarely or never post. Coverage
          looks thin compared to the U.S. Senate not because the collector
          is failing but because the publishing pattern is different.
        </p>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-3">
          Texas releases are mostly published as linked PDFs rather than HTML
          pages, so the archive captures the listing entry (title, date,
          source URL) but defers the body text to the original PDF.
        </p>
      </section>

      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          Data sourcing
        </h2>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-3">
          All data is sourced from official senator websites on senate.gov.
          Press releases are public records published by Senate offices for
          public consumption. This project collects, normalizes and indexes
          that information to make it searchable and analyzable. No private
          or restricted data is used.
        </p>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-3">
          The senator list is sourced from senate.gov&apos;s official member
          directory. Party and state reflect the 119th Congress. The House
          list (437 members) comes from congress.gov and the{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-xs text-neutral-500">
            unitedstates/congress-legislators
          </code>{" "}
          repository.
        </p>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl">
          Scraping runs at a polite rate (one concurrent request per domain,
          half-second to 1.5-second delays). No login credentials, CAPTCHA
          circumvention or rate-limit evasion is used. Requests identify
          themselves with standard browser headers.
        </p>
      </section>

      {/* Stack */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          Stack
        </h2>
        <div className="text-sm text-neutral-600 space-y-2">
          <StackItem
            label="Pipeline"
            value="Python 3.14, httpx, BeautifulSoup + lxml, Playwright, feedparser"
          />
          <StackItem
            label="Database"
            value="Postgres (Neon) with tsvector full-text search"
          />
          <StackItem
            label="Frontend"
            value="Next.js 16, React 19, Tailwind CSS 4, TypeScript, D3"
          />
          <StackItem label="Hosting" value="Vercel (frontend), Neon (database)" />
          <StackItem
            label="Source code"
            value="github.com/tbrown034/capitol-releases"
          />
          <StackItem label="Data window" value="January 1, 2025 to present" />
        </div>
      </section>

      {/* Open source + contact */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          Open source
        </h2>
        <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl">
          Capitol Releases is open source. Code, pipeline and documentation
          are on{" "}
          <a
            href="https://github.com/tbrown034/capitol-releases"
            className="underline underline-offset-2 text-neutral-900 hover:text-neutral-600 transition-colors"
          >
            GitHub
          </a>
          . Found a bug or a data error?{" "}
          <a
            href="https://github.com/tbrown034/capitol-releases/issues"
            className="underline underline-offset-2 text-neutral-900 hover:text-neutral-600 transition-colors"
          >
            Open an issue
          </a>{" "}
          or email{" "}
          <a
            href="mailto:trevorbrown.web@gmail.com"
            className="underline underline-offset-2 text-neutral-900 hover:text-neutral-600 transition-colors"
          >
            trevorbrown.web@gmail.com
          </a>
          .
        </p>
      </section>

      {/* Related */}
      <section className="mb-12">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
          Related resources
        </h2>
        <ul className="text-sm text-neutral-600 space-y-2">
          <Resource
            href="https://www.senate.gov/senators/"
            title="U.S. Senate member directory"
            description="Official list of current senators."
          />
          <Resource
            href="https://www.congress.gov/"
            title="Congress.gov"
            description="Legislation, floor activity and committee records."
          />
          <Resource
            href="https://github.com/unitedstates/congress-legislators"
            title="unitedstates/congress-legislators"
            description="Open data on every member of Congress, past and present."
          />
        </ul>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number | string;
  suffix?: string;
}) {
  return (
    <div className="bg-white p-4">
      <p className="text-[11px] uppercase tracking-wider text-neutral-500">
        {label}
      </p>
      <p className="mt-1 font-[family-name:var(--font-dm-mono)] tabular-nums text-xl text-neutral-900">
        {typeof value === "number" ? value.toLocaleString() : value}
        {suffix && (
          <span className="ml-1.5 text-xs text-neutral-500 font-normal">
            {suffix}
          </span>
        )}
      </p>
    </div>
  );
}

function CoverageBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    complete: "text-emerald-700 bg-emerald-50 border-emerald-200",
    partial: "text-amber-700 bg-amber-50 border-amber-200",
    undated: "text-blue-700 bg-blue-50 border-blue-200",
    empty: "text-rose-700 bg-rose-50 border-rose-200",
  };
  return (
    <span
      className={`inline-flex border px-2 py-0.5 text-[10px] uppercase tracking-wider ${styles[status] ?? "text-neutral-600 bg-neutral-50 border-neutral-200"}`}
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
      <div className="flex h-7 w-7 shrink-0 items-center justify-center bg-neutral-900 text-xs font-[family-name:var(--font-dm-mono)] text-white">
        {number}
      </div>
      <div>
        <h4 className="text-sm font-medium text-neutral-900">{title}</h4>
        <p className="mt-1 text-sm text-neutral-600 leading-relaxed max-w-2xl">
          {description}
        </p>
      </div>
    </div>
  );
}

function StackItem({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-start gap-4">
      <span className="w-28 shrink-0 text-neutral-900 font-medium">
        {label}
      </span>
      <span className="text-neutral-600">{value}</span>
    </div>
  );
}

function Resource({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <li>
      <a
        href={href}
        target="_blank"
        rel="noopener noreferrer"
        className="underline underline-offset-2 text-neutral-900 hover:text-neutral-600 transition-colors"
      >
        {title}
      </a>
      <span className="text-neutral-300"> — </span>
      <span className="text-neutral-500">{description}</span>
    </li>
  );
}
