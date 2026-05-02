import Link from "next/link";
import { getSocialFeed, getSocialStats, getSocialActiveSenators } from "../lib/queries";
import { getSenatorPhotoUrl, getInitials, getSenatorHref } from "../lib/photos";
import type { SocialFeedItem } from "../lib/db";

export const metadata = {
  title: "Social — Capitol Releases",
  description:
    "Senator-authored Bluesky posts, archived since January 1, 2026. Separate from the press release corpus.",
};

export const revalidate = 300;

const PER_PAGE = 50;

export default async function SocialPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | undefined>>;
}) {
  const params = await searchParams;
  const page = Math.max(1, Number(params.page ?? "1"));
  const party = ["D", "R", "I"].includes(params.party ?? "") ? params.party : undefined;
  const state = params.state;
  const officialId = params.senator;
  const includeReplies = params.replies === "1";

  const filters = {
    party,
    state,
    officialId,
    includeReplies,
  };
  const [feed, stats, active] = await Promise.all([
    getSocialFeed({ page, perPage: PER_PAGE, ...filters }),
    getSocialStats(filters),
    getSocialActiveSenators(),
  ]);

  const totalPages = Math.max(1, Math.ceil(feed.total / PER_PAGE));

  function buildHref(overrides: Record<string, string | undefined>) {
    const merged: Record<string, string | undefined> = {
      page: page > 1 ? String(page) : undefined,
      party,
      state,
      senator: officialId,
      replies: includeReplies ? "1" : undefined,
      ...overrides,
    };
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(merged)) {
      if (v !== undefined && v !== "") sp.set(k, v);
    }
    const qs = sp.toString();
    return qs ? `/social?${qs}` : "/social";
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-10">
      <div className="mb-3">
        <span className="inline-block text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-100 text-amber-900 border border-amber-200">
          Beta — separate from main feed
        </span>
      </div>
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Social
      </h1>
      <SummaryLine
        stats={stats}
        filtered={Boolean(party || state || officialId || includeReplies)}
        senatorName={officialId ? active.find((a) => a.official_id === officialId)?.full_name : undefined}
        party={party}
        includeReplies={includeReplies}
      />
      <p className="text-xs text-neutral-500 leading-relaxed mb-8 max-w-2xl">
        Verified handles only — confirmed via senate.gov footer link, .senate.gov
        domain handle, or appearance in two or more independent curated starter
        packs. Republican accounts that meet that bar are eligible; almost none
        currently exist on the platform.
      </p>

      <Filters
        party={party}
        state={state}
        officialId={officialId}
        includeReplies={includeReplies}
        active={active}
        buildHref={buildHref}
      />

      <ul className="divide-y divide-neutral-200 border-t border-neutral-200">
        {feed.items.map((post) => (
          <PostRow key={post.id} post={post} />
        ))}
        {feed.items.length === 0 && (
          <li className="py-10 text-center text-sm text-neutral-500">
            No posts match these filters.
          </li>
        )}
      </ul>

      {feed.items.length > 0 && (
        <Pagination page={page} totalPages={totalPages} buildHref={buildHref} total={feed.total} />
      )}
    </div>
  );
}

function Filters({
  party,
  officialId,
  includeReplies,
  active,
  buildHref,
}: {
  party: string | undefined;
  state: string | undefined;
  officialId: string | undefined;
  includeReplies: boolean;
  active: { official_id: string; full_name: string; party: "D" | "R" | "I"; state: string; post_count: number }[];
  buildHref: (overrides: Record<string, string | undefined>) => string;
}) {
  const top = active.slice(0, 12);
  return (
    <div className="space-y-3 mb-6">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <FilterPill label="All" active={!party && !officialId} href={buildHref({ party: undefined, senator: undefined, page: undefined })} />
        <FilterPill label="Democrats" active={party === "D"} href={buildHref({ party: "D", senator: undefined, page: undefined })} />
        <FilterPill label="Republicans" active={party === "R"} href={buildHref({ party: "R", senator: undefined, page: undefined })} />
        <FilterPill label="Independents" active={party === "I"} href={buildHref({ party: "I", senator: undefined, page: undefined })} />
        <span className="text-neutral-300 mx-1">|</span>
        <FilterPill
          label={includeReplies ? "Replies on" : "Replies off"}
          active={includeReplies}
          href={buildHref({ replies: includeReplies ? undefined : "1", page: undefined })}
        />
      </div>
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="text-neutral-500 mr-1">Most active:</span>
        {top.map((s) => (
          <FilterPill
            key={s.official_id}
            label={`${s.full_name.split(" ").slice(-1)[0]} ${s.post_count}`}
            active={officialId === s.official_id}
            href={buildHref({
              senator: officialId === s.official_id ? undefined : s.official_id,
              party: undefined,
              page: undefined,
            })}
          />
        ))}
      </div>
    </div>
  );
}

function FilterPill({ label, active, href }: { label: string; active: boolean; href: string }) {
  return (
    <Link
      href={href}
      className={
        active
          ? "px-2.5 py-1 rounded-full text-xs bg-neutral-900 text-white"
          : "px-2.5 py-1 rounded-full text-xs border border-neutral-300 text-neutral-600 hover:text-neutral-900 hover:border-neutral-900"
      }
    >
      {label}
    </Link>
  );
}

function PostRow({ post }: { post: SocialFeedItem }) {
  const dt = new Date(post.created_at);
  const datePretty = dt.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: dt.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined,
  });
  const timePretty = dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const partyClass =
    post.party === "D"
      ? "text-blue-700"
      : post.party === "R"
        ? "text-red-700"
        : "text-neutral-700";
  const photo = getSenatorPhotoUrl(post.official_id);
  const senatorHref = getSenatorHref(post.official_id);
  // AT URI looks like at://did:plc:.../app.bsky.feed.post/<rkey>
  const rkey = post.platform_post_id.split("/").pop();
  const bskyUrl = rkey ? `https://bsky.app/profile/${post.handle}/post/${rkey}` : `https://bsky.app/profile/${post.handle}`;

  return (
    <li className="py-4 flex gap-3">
      <Link href={senatorHref} className="shrink-0">
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={photo}
            alt={post.senator_name}
            className="w-10 h-10 rounded-full object-cover bg-neutral-100"
            loading="lazy"
          />
        ) : (
          <div className="w-10 h-10 rounded-full bg-neutral-200 flex items-center justify-center text-xs text-neutral-700">
            {getInitials(post.senator_name)}
          </div>
        )}
      </Link>
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5 text-sm flex-wrap">
          <Link href={senatorHref} className="font-medium text-neutral-900 hover:underline">
            {post.senator_name}
          </Link>
          <span className={`text-xs ${partyClass}`}>
            {post.party}–{post.state}
          </span>
          <span className="text-xs text-neutral-400">·</span>
          <a
            href={bskyUrl}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-neutral-500 hover:text-neutral-900 hover:underline"
          >
            @{post.handle}
          </a>
          <span className="text-xs text-neutral-400">·</span>
          <span className="text-xs text-neutral-500">
            {datePretty} {timePretty}
          </span>
          {post.is_reply && (
            <span className="text-[10px] uppercase tracking-wider text-neutral-400">reply</span>
          )}
        </div>
        <p className="text-[15px] leading-relaxed text-neutral-800 whitespace-pre-wrap mt-1">
          {post.text}
        </p>
        {post.embed_summary && (
          <p className="text-xs text-neutral-500 mt-1 truncate">{post.embed_summary}</p>
        )}
      </div>
    </li>
  );
}

function Pagination({
  page,
  totalPages,
  buildHref,
  total,
}: {
  page: number;
  totalPages: number;
  buildHref: (overrides: Record<string, string | undefined>) => string;
  total: number;
}) {
  return (
    <div className="mt-8 flex items-center justify-between text-sm text-neutral-600">
      <span>
        Page {page} of {totalPages.toLocaleString()} · {total.toLocaleString()} posts
      </span>
      <div className="flex gap-2">
        {page > 1 && (
          <Link
            href={buildHref({ page: page === 2 ? undefined : String(page - 1) })}
            className="px-3 py-1 border border-neutral-300 rounded hover:border-neutral-900"
          >
            ← Prev
          </Link>
        )}
        {page < totalPages && (
          <Link
            href={buildHref({ page: String(page + 1) })}
            className="px-3 py-1 border border-neutral-300 rounded hover:border-neutral-900"
          >
            Next →
          </Link>
        )}
      </div>
    </div>
  );
}

function SummaryLine({
  stats,
  filtered,
  senatorName,
  party,
  includeReplies,
}: {
  stats: { total: number; senators_active: number; party: { D: number; R: number; I: number } };
  filtered: boolean;
  senatorName: string | undefined;
  party: string | undefined;
  includeReplies: boolean;
}) {
  const total = stats.total.toLocaleString();
  const senatorWord = stats.senators_active === 1 ? "senator" : "senators";
  const lede = filtered ? "Showing" : "Senator-authored Bluesky posts since January 1, 2026.";
  const partyLabel = party === "D" ? "Democrats" : party === "R" ? "Republicans" : party === "I" ? "Independents" : null;

  if (senatorName) {
    return (
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Showing {total} {includeReplies ? "posts and replies" : "posts"} from{" "}
        <span className="text-neutral-900 font-medium">{senatorName}</span>.
      </p>
    );
  }

  if (partyLabel) {
    return (
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        Showing {total} {includeReplies ? "posts and replies" : "posts"} from{" "}
        <span className="text-neutral-900 font-medium">{partyLabel}</span> ({stats.senators_active}{" "}
        {senatorWord}).
        {party === "R" && stats.total === 0 && (
          <> No verified Republican senator handles currently exist on Bluesky.</>
        )}
      </p>
    );
  }

  return (
    <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
      {lede} {total} {includeReplies ? "posts and replies" : "posts"} from{" "}
      {stats.senators_active} {senatorWord} ({stats.party.D} D, {stats.party.I} I,{" "}
      {stats.party.R} R).{" "}
      {!includeReplies && "Replies and reposts excluded by default."}
    </p>
  );
}
