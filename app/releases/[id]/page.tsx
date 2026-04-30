import { notFound } from "next/navigation";
import Link from "next/link";
import {
  getReleaseById,
  getRelatedReleases,
  getReleaseVersions,
  CONTENT_TYPE_LABEL,
} from "../../lib/queries";
import { ReleaseCard } from "../../components/release-card";
import { TypeBadge } from "../../components/type-badge";
import { getSenatorPhotoUrl, getInitials, getSenatorHref } from "../../lib/photos";
import { normalizeTitle } from "../../lib/titles";
import { STATE_NAMES } from "../../lib/states";
import { formatReleaseDate, formatTimestamp, isFutureDated } from "../../lib/dates";

export const revalidate = 600;

function sourceHost(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "senate.gov";
  }
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const release = await getReleaseById(id);
  if (!release) return { title: "Not Found" };
  const title = normalizeTitle(release.title);
  return {
    title: `${title} — ${release.senator_name}`,
    description: `${CONTENT_TYPE_LABEL[release.content_type]} from ${release.senator_name} (${release.party}-${release.state}), ${formatReleaseDate(release.published_at)}.`,
    openGraph: {
      title,
      description: `${release.senator_name} (${release.party}-${release.state}) · ${formatReleaseDate(release.published_at)}`,
      type: "article",
    },
    alternates: {
      canonical: release.source_url,
    },
  };
}

function renderBody(text: string | null) {
  if (!text) return null;
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => p.trim())
    .filter(Boolean);
  return paragraphs.map((p, i) => (
    <p key={i} className="mb-4 last:mb-0">
      {p.split(/\n/).map((line, j, arr) => (
        <span key={j}>
          {line}
          {j < arr.length - 1 && <br />}
        </span>
      ))}
    </p>
  ));
}

export default async function ReleasePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const release = await getReleaseById(id);
  if (!release) notFound();

  const [related, versions] = await Promise.all([
    getRelatedReleases(release, 6),
    release.version_count > 0 ? getReleaseVersions(release.id) : Promise.resolve([]),
  ]);

  const photo = getSenatorPhotoUrl(release.senator_name, release.senator_id);
  const partyLabel =
    release.party === "D"
      ? "Democrat"
      : release.party === "R"
        ? "Republican"
        : "Independent";
  const partyColor =
    release.party === "D"
      ? "text-blue-600"
      : release.party === "R"
        ? "text-red-600"
        : "text-amber-600";
  const partyRing =
    release.party === "D"
      ? "ring-blue-500"
      : release.party === "R"
        ? "ring-red-500"
        : "ring-amber-500";
  const host = sourceHost(release.source_url);
  const isDeleted = release.deleted_at !== null;
  const isFuture = isFutureDated(release.published_at, release.scraped_at);
  const title = normalizeTitle(release.title);
  // Detect chamber from senator_id prefix so back-link and copy match.
  const isTexas = release.senator_id.startsWith("tx-");
  const backHref = isTexas ? "/texas/feed" : "/feed";
  const backLabel = isTexas ? "← Back to Texas feed" : "← Back to feed";

  return (
    <article className="mx-auto max-w-3xl px-4 py-12">
      <Link
        href={backHref}
        className="text-sm text-neutral-500 hover:text-neutral-900 transition-colors"
      >
        {backLabel}
      </Link>

      {isFuture && (
        <div className="mt-6 border-l-4 border-amber-400 bg-amber-50 px-4 py-3">
          <p className="text-sm text-amber-900">
            <span className="font-semibold">Date discrepancy.</span>{" "}
            The senator&apos;s office published this release with a date of{" "}
            <time dateTime={release.published_at!}>
              {formatReleaseDate(release.published_at)}
            </time>
            , but Capitol Releases captured it on{" "}
            <time dateTime={release.scraped_at}>
              {formatReleaseDate(release.scraped_at)}
            </time>
            . The published date appears to be a typo on the source site; the
            capture timestamp is when the release first appeared at the URL
            below.
          </p>
        </div>
      )}

      {isDeleted && (
        <div className="mt-6 border-l-4 border-amber-400 bg-amber-50 px-4 py-3">
          <p className="text-sm text-amber-900">
            <span className="font-semibold">No longer reachable on{" "}{host}.</span>{" "}
            The source URL stopped resolving on repeated checks (first noted{" "}
            <time dateTime={release.deleted_at!}>
              {formatReleaseDate(release.deleted_at)}
            </time>
            ). Could be a redesign, a CDN issue, or an intentional removal &mdash;
            we don&apos;t treat it as proof of any of those. The captured copy
            remains in the archive as of{" "}
            <time dateTime={release.scraped_at}>
              {formatTimestamp(release.scraped_at)}
            </time>
            .
          </p>
        </div>
      )}

      {/* Senator strip */}
      <div className="mt-6 flex items-center gap-3">
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photo}
            alt={`${release.senator_name} (${release.party}-${release.state})`}
            width={40}
            height={40}
            className={`h-10 w-10 rounded-full object-cover ring-1 ${partyRing}`}
          />
        ) : (
          <span
            className={`flex h-10 w-10 items-center justify-center rounded-full bg-neutral-100 text-xs font-medium text-neutral-500 ring-1 ${partyRing}`}
          >
            {getInitials(release.senator_name)}
          </span>
        )}
        <div className="text-sm">
          <Link
            href={getSenatorHref(release.senator_id)}
            className="font-[family-name:var(--font-source-serif)] text-base text-neutral-900 hover:underline"
          >
            {release.senator_name}
          </Link>
          <div className="text-xs text-neutral-500">
            <span className={partyColor}>{partyLabel}</span>
            <span className="mx-1.5 text-neutral-300">·</span>
            <span>{STATE_NAMES[release.state] ?? release.state}</span>
          </div>
        </div>
      </div>

      {/* Headline */}
      <h1 className="mt-6 font-[family-name:var(--font-source-serif)] text-3xl leading-tight text-neutral-900">
        {title}
      </h1>

      {/* Date + type + source */}
      <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-neutral-500 border-b border-neutral-200 pb-4">
        {release.published_at && (
          <time
            dateTime={release.published_at}
            className="font-[family-name:var(--font-dm-mono)] tabular-nums"
          >
            {formatReleaseDate(release.published_at)}
          </time>
        )}
        <TypeBadge type={release.content_type} size="sm" />
        <span className="ml-auto flex items-center gap-3">
          <a
            href={release.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 border border-neutral-300 px-2.5 py-1 text-xs text-neutral-700 hover:border-neutral-900 hover:text-neutral-900 transition-colors"
            title={`Open original on ${host}`}
          >
            View on {host}
            <span aria-hidden>↗</span>
          </a>
        </span>
      </div>

      {/* Body */}
      <div className="prose prose-neutral mt-6 max-w-none text-neutral-800 leading-relaxed">
        {release.body_text ? (
          <div className="text-base">{renderBody(release.body_text)}</div>
        ) : isTexas && release.source_url.includes("videoplayer.php") ? (
          <div className="rounded-md border border-neutral-200 bg-neutral-50 px-5 py-5 text-sm text-neutral-700 leading-relaxed">
            <p className="mb-3">
              <span className="font-medium text-neutral-900">Video press conference.</span>{" "}
              This is a videoplayer.php item rather than a written press
              release; the content lives off-platform. We archive the listing
              entry and link out.
            </p>
            <a
              href={release.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 border border-neutral-700 px-3 py-1.5 text-xs text-neutral-700 hover:bg-neutral-900 hover:text-white transition-colors"
            >
              Watch on senate.texas.gov
              <span aria-hidden> ↗</span>
            </a>
          </div>
        ) : (
          <p className="text-sm text-neutral-500 italic">
            No body text was captured for this release. Read it on{" "}
            <a
              href={release.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="underline hover:text-neutral-900"
            >
              {host}
            </a>
            .
          </p>
        )}
      </div>

      {/* Provenance footer */}
      <div className="mt-10 border-t border-neutral-200 pt-6 text-xs text-neutral-500 space-y-1.5">
        <div>
          <span className="uppercase tracking-wider text-neutral-400">Source: </span>
          <a
            href={release.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-neutral-700 hover:text-neutral-900 hover:underline break-all"
          >
            {release.source_url}
            <span aria-hidden> ↗</span>
          </a>
        </div>
        <div>
          <span className="uppercase tracking-wider text-neutral-400">Captured: </span>
          <time
            dateTime={release.scraped_at}
            className="font-[family-name:var(--font-dm-mono)] tabular-nums"
          >
            {formatTimestamp(release.scraped_at)}
          </time>
        </div>
        {release.last_seen_live && !isDeleted && (
          <div>
            <span className="uppercase tracking-wider text-neutral-400">Last seen live: </span>
            <time
              dateTime={release.last_seen_live}
              className="font-[family-name:var(--font-dm-mono)] tabular-nums"
            >
              {formatTimestamp(release.last_seen_live)}
            </time>
          </div>
        )}
        <div>
          <span className="uppercase tracking-wider text-neutral-400">Record ID: </span>
          <code className="font-[family-name:var(--font-dm-mono)] text-neutral-600">
            {release.id}
          </code>
        </div>
      </div>

      {/* Version history */}
      {versions.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
            Edit history ({versions.length} prior {versions.length === 1 ? "version" : "versions"})
          </h2>
          <p className="text-xs text-neutral-500 mb-4">
            This release was edited after publication. Earlier captures are
            preserved below.
          </p>
          <ol className="space-y-4">
            {versions.map((v) => (
              <li
                key={v.id}
                className="border-l-2 border-neutral-300 pl-4"
              >
                <div className="text-xs font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-500 mb-1">
                  Captured {formatTimestamp(v.captured_at)}
                </div>
                {v.body_text ? (
                  <details className="text-sm text-neutral-700">
                    <summary className="cursor-pointer text-neutral-500 hover:text-neutral-900 transition-colors">
                      Show prior body text
                    </summary>
                    <div className="mt-3 whitespace-pre-wrap rounded border border-neutral-200 bg-neutral-50 p-3 text-[13px] leading-relaxed">
                      {v.body_text}
                    </div>
                  </details>
                ) : (
                  <span className="text-xs text-neutral-500 italic">
                    Body text not preserved for this version.
                  </span>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}

      {/* Related releases */}
      {related.length > 0 && (
        <section className="mt-10">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
            Issued within 24 hours
          </h2>
          <p className="text-xs text-neutral-500 mb-3">
            Other senators&apos; releases published in the day before or after this one.
          </p>
          <div>
            {related.map((r) => (
              <ReleaseCard key={r.id} item={r} />
            ))}
          </div>
        </section>
      )}
    </article>
  );
}
