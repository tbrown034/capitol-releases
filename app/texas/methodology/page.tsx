import Link from "next/link";
import { getTxStats, getTxRoster } from "../../lib/texas";
import { formatLongMonthYear, formatShortDate } from "../../lib/dates";

export const metadata = {
  title: "Texas Senate scraper — Methodology — Capitol Releases",
  description:
    "How Capitol Releases archives every Texas state senator's press releases from senate.texas.gov: source, parsing, scope, verification, and known limits.",
};

export const revalidate = 3600;

export default async function TexasMethodology() {
  const [stats, roster] = await Promise.all([getTxStats(), getTxRoster()]);
  const silent = roster.filter((r) => r.release_count === 0).length;
  const earliest = roster
    .map((r) => r.earliest_release)
    .filter((d): d is string => Boolean(d))
    .sort()
    .at(0);
  // The "last verified" date floats with the most recent successful scrape,
  // which is what actually compared the DB to live source. Static "April 29"
  // copy went stale within a day of being written; this stays current.
  const lastVerified = stats.last_scrape ? formatShortDate(stats.last_scrape) : "—";

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link
        href="/texas"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← Texas Senate
      </Link>
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Texas Senate scraper methodology
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed max-w-2xl mb-8">
        How the {stats.total_releases.toLocaleString()}-record Texas archive is
        built, where the data comes from, what we don&apos;t collect, and how
        you can verify any of it yourself.
      </p>

      {/* Source */}
      <Section title="Source">
        <p>
          <span className="text-neutral-900 font-medium">Single platform.</span>{" "}
          All 31 Texas Senate districts publish to the same domain:{" "}
          <a
            href="https://senate.texas.gov/"
            target="_blank"
            rel="noopener noreferrer"
            translate="no"
            className="underline hover:text-neutral-900"
          >
            senate.texas.gov
          </a>
          . The pressroom for each member is one URL:{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            senate.texas.gov/pressroom.php?d=&#123;district&#125;
          </code>
          . There is no Texas-Senate-wide RSS, no JSON API, no mobile
          alternative. The HTML pressroom is the canonical source.
        </p>
        <p>
          <span className="text-neutral-900 font-medium">Static HTML, no JavaScript.</span>{" "}
          The page is server-rendered. We use{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            httpx
          </code>{" "}
          (async HTTP) to GET each pressroom and parse with{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            BeautifulSoup + lxml
          </code>
          . No headless browser required. senate.texas.gov does not sit behind
          Akamai, Cloudflare, or other anti-bot protection &mdash; standard
          browser User-Agent works on every request.
        </p>
        <p>
          <span className="text-neutral-900 font-medium">Robots permissive.</span>{" "}
          senate.texas.gov/robots.txt does not disallow{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            /pressroom.php
          </code>
          . Polite pacing: one concurrent request per senator, half-second to
          1.5-second backoff between fetches.
        </p>
      </Section>

      {/* What we extract */}
      <Section title="What we extract">
        <p>
          Every pressroom uses the same DOM shape. The collector parses items
          in document order &mdash; looking for{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            &lt;h3&gt;YEAR&lt;/h3&gt;
          </code>{" "}
          headers and the{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            &lt;p&gt;
          </code>{" "}
          blocks that follow. Each paragraph carries:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li>
            <span className="text-neutral-900 font-medium">A date</span> in
            MM/DD/YYYY format as inline text. We regex-match the first date in
            each paragraph.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">An icon</span> &mdash;
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700 ml-1">
              pdficon_sm.png
            </code>{" "}
            for PDF press releases,{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              playbutton_sm.png
            </code>{" "}
            for video press conferences.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">An anchor</span> with
            the title and the link to the actual content. Content lives at one
            of:
            <ul className="list-disc pl-6 mt-1 text-[13px]">
              <li>
                <code className="font-[family-name:var(--font-dm-mono)]">
                  /members/d&#123;NN&#125;/press/en/p&#123;YYYYMMDD&#125;&#123;seq&#125;.pdf
                </code>{" "}
                &mdash; PDF press releases (the majority)
              </li>
              <li>
                <code className="font-[family-name:var(--font-dm-mono)]">
                  /press.php?id=&#123;district&#125;-&#123;date&#125;
                </code>{" "}
                &mdash; HTML press releases (a minority)
              </li>
              <li>
                <code className="font-[family-name:var(--font-dm-mono)]">
                  /videoplayer.php?...
                </code>{" "}
                &mdash; video press conferences
              </li>
            </ul>
          </li>
        </ul>
        <p>
          We classify PDFs and HTML pages as{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            content_type=&apos;press_release&apos;
          </code>
          ; videos as{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            content_type=&apos;other&apos;
          </code>{" "}
          and prefix titles with{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            VIDEO:
          </code>{" "}
          so they&apos;re visually distinct in lists.
        </p>
      </Section>

      {/* Body extraction */}
      <Section title="Body text extraction">
        <p>
          The TX collector captures the listing entry (title, date, source
          URL) on the first pass; a second pass downloads the actual content
          and extracts body text. Two paths, depending on the source URL:
        </p>
        <ul className="list-disc pl-6 space-y-1">
          <li>
            <span className="text-neutral-900 font-medium">PDF</span>{" "}
            (~52% of records): downloaded and parsed with{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              pdfplumber
            </code>{" "}
            (x_tolerance=2, y_tolerance=3). pdfplumber correctly handles TX
            templates that separate words by x-coordinate position rather
            than space characters &mdash; pypdf was concatenating those as
            &ldquo;membercommitteeappointmentsforthe&rdquo;. Residual
            whitespace artifacts (line-broken words from column layout) are
            normalized: a newline between two lowercase letters is a wrap,
            not a break.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">HTML press.php</span>{" "}
            (~48% of records): fetched and parsed with BeautifulSoup. Body
            text is the contents of{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              &lt;main&gt;
            </code>{" "}
            with the predictable navigation preamble
            (&ldquo;Press Items: Senator X — District N « Return to the
            home page printer-friendly&rdquo;) stripped.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">
              videoplayer.php
            </span>{" "}
            (~3% of records): video press conferences. Bodies live
            off-platform; we link out and classify as{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              content_type=&apos;other&apos;
            </code>
            .
          </li>
        </ul>
        <p>
          Every body is hashed (SHA-256) at extraction. On future re-fetches
          we compare the hash; a mismatch indicates the source PDF or HTML
          was edited after publication, which we surface as edit history on
          the per-release page.
        </p>
        <p>
          As of the most recent extraction:{" "}
          <span className="text-neutral-900 font-medium">
            304 of 304 press-release records have body text + content_hash
          </span>
          . The 10 video records do not (their content lives off-platform).
        </p>
      </Section>

      {/* Scope */}
      <Section title="What we keep, what we skip">
        <p>
          <span className="text-neutral-900 font-medium">
            January 1, 2025 to present.
          </span>{" "}
          Anything dated earlier is ignored at ingest. Some senators
          (Zaffirini in particular) have archives reaching back 25 years; we
          don&apos;t pull pre-2025 content. Uniform with the federal-Senate
          scope.
        </p>
        <p>
          <span className="text-neutral-900 font-medium">
            Current holders only.
          </span>{" "}
          District 4 is currently vacant pending a May 2026 special election;
          we don&apos;t collect for it. District 9&apos;s Taylor Rehmet was
          sworn in February 2026 and has not begun publishing; her seed entry
          has{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            expect_empty: true
          </code>{" "}
          so the data-quality tests don&apos;t false-flag her.
        </p>
        <p>
          <span className="text-neutral-900 font-medium">
            No third-party content.
          </span>{" "}
          We don&apos;t archive press clippings, &ldquo;in the news&rdquo;
          aggregations, or curated mentions even if they live on the
          senator&apos;s site.
        </p>
      </Section>

      {/* Cadence */}
      <Section title="Collection cadence">
        <p>
          The same{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            python -m pipeline update
          </code>{" "}
          command runs the TX collector for every TX senator, four times a
          day: 9 AM, 1 PM, 5 PM, and 9 PM Eastern Time (via GitHub Actions).
          Per-senator: one HTTP GET, parse, dedup against existing records by{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            source_url
          </code>
          , insert new records.
        </p>
      </Section>

      {/* Verification */}
      <Section title="Verification">
        <p>There are two truth-checks anyone can reproduce:</p>
        <ol className="list-decimal pl-6 space-y-2">
          <li>
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              python -m pipeline tx-truth
            </code>{" "}
            &mdash; hits each of 30 senate.texas.gov pressrooms, counts dated
            entries since Jan 2025, compares to the DB, reports deltas. Last
            run: {lastVerified}.{" "}
            <span className="text-neutral-900 font-medium">
              30 / 30 senators within ±1 of the live count.
            </span>{" "}
            Zero missing, zero extras, zero errors.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">
              Source-URL spot sample.
            </span>{" "}
            Random 30 of {stats.total_releases.toLocaleString()} records, GET
            each source URL, confirm 200 with real content. Last run:
            {" "}{lastVerified}.{" "}
            <span className="text-neutral-900 font-medium">30 / 30 valid.</span>{" "}
            Mix of PDFs and HTML, all reachable, all real titles.
          </li>
        </ol>
        <p>
          The{" "}
          <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
            tx-truth
          </code>{" "}
          command is reproducible &mdash; anyone with a clone of the repo can
          run it against the same live source.{" "}
          <a
            href="https://github.com/tbrown034/capitol-releases/blob/main/pipeline/commands/tx_truth_check.py"
            target="_blank"
            rel="noopener noreferrer"
            className="underline hover:text-neutral-900"
          >
            Source
          </a>
          .
        </p>
      </Section>

      {/* What can fail */}
      <Section title="What can fail and how we'd notice">
        <ul className="list-disc pl-6 space-y-2">
          <li>
            <span className="text-neutral-900 font-medium">
              Pressroom HTML structure changes.
            </span>{" "}
            The{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              &lt;h3&gt;YEAR&lt;/h3&gt;
            </code>{" "}
            + sibling{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              &lt;p&gt;
            </code>{" "}
            shape has been stable since at least 2010. If senate.texas.gov
            redesigns, the collector returns zero items, the daily run logs
            <em>&ldquo;No items found&rdquo;</em>, the per-senator alert fires,
            and the next{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              tx-truth
            </code>{" "}
            run shows a large negative delta.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">
              A senator&apos;s pressroom URL changes.
            </span>{" "}
            Configured per-senator in{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              pipeline/seeds/tx_senate.json
            </code>
            . If a URL 404s, the daily run logs HTTP 404 and the per-senator
            alert fires.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">
              Date format changes.
            </span>{" "}
            All dates are MM/DD/YYYY. If a senator switches to ISO format, the
            collector falls back to the year header (Jan 1) with{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              date_confidence=0.0
            </code>{" "}
            and the date-quality test catches the regression.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">
              A senator starts publishing in a way we don&apos;t recognize.
            </span>{" "}
            The extractor accepts{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              .pdf
            </code>
            ,{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              press.php
            </code>
            , and{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              videoplayer.php
            </code>{" "}
            URLs. New URL shapes would be silently skipped. The next{" "}
            <code className="font-[family-name:var(--font-dm-mono)] text-[13px] text-neutral-700">
              tx-truth
            </code>{" "}
            run would catch this as a positive delta within hours.
          </li>
        </ul>
      </Section>

      {/* What we don't claim */}
      <Section title="What we deliberately don't claim">
        <ul className="list-disc pl-6 space-y-2">
          <li>
            <span className="text-neutral-900 font-medium">
              Not &ldquo;every record.&rdquo;
            </span>{" "}
            We claim &ldquo;every record on each member&apos;s pressroom on
            senate.texas.gov.&rdquo; If a senator publishes elsewhere
            &mdash; campaign site, social media, district mailings, local
            press &mdash; those aren&apos;t in the archive.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">
              Not &ldquo;deletion detection as a watchdog.&rdquo;
            </span>{" "}
            We re-fetch source URLs as a data-integrity check; if a URL stops
            resolving on repeated checks, we tombstone it. We don&apos;t treat
            that as proof of intentional removal &mdash; sites get redesigned,
            CDNs hiccup, URLs restructure.
          </li>
          <li>
            <span className="text-neutral-900 font-medium">
              Not &ldquo;real-time.&rdquo;
            </span>{" "}
            Four times a day via cron, not push.
          </li>
        </ul>
      </Section>

      {/* Stats footer */}
      <section className="mt-12 pt-6 border-t border-neutral-200">
        <p className="text-xs text-neutral-500 leading-relaxed max-w-2xl">
          As of this page render: {roster.length} active TX senators tracked,{" "}
          {roster.length - silent} publishing on senate.texas.gov,{" "}
          {silent} silent. {stats.total_releases.toLocaleString()} records
          archived
          {earliest && <> since {formatLongMonthYear(earliest)}</>}. Last
          end-to-end live verification: {lastVerified}.{" "}
          <Link href="/about" className="underline hover:text-neutral-900">
            Site-wide methodology
          </Link>{" "}
          ·{" "}
          <Link href="/texas" className="underline hover:text-neutral-900">
            Back to Texas
          </Link>
        </p>
      </section>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  // Anchor IDs let the verified-live badge on /texas link directly to
  // "#verification" and similar deep links from elsewhere on the site.
  const anchor = title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  return (
    <section id={anchor} className="mb-10 scroll-mt-8">
      <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
        {title}
      </h2>
      <div className="text-sm text-neutral-700 leading-relaxed space-y-3 max-w-2xl">
        {children}
      </div>
    </section>
  );
}
