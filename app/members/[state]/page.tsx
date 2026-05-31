import Link from "next/link";
import Image from "next/image";
import { notFound } from "next/navigation";
import { getSenators, getHouseMembers, getFeed } from "../../lib/queries";
import { sql } from "../../lib/db";
import { STATE_NAMES } from "../../lib/states";
import { ReleaseCard } from "../../components/release-card";
import { formatMonthYear } from "../../lib/dates";
import type { SenatorWithCount } from "../../lib/db";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ state: string }>;
}) {
  const { state } = await params;
  const code = state.toUpperCase();
  const name = STATE_NAMES[code];
  if (!name) return { title: "Members — Capitol Releases" };
  return {
    title: `${name} delegation — Capitol Releases`,
    description: `Senators and U.S. House members representing ${name}, with their recent press releases, statements, and op-eds.`,
  };
}

function formatDistrict(d: string | null | undefined): string {
  if (!d) return "At-Large";
  const n = Number(d);
  return Number.isFinite(n) ? `District ${n}` : d;
}

function partyClass(p: "D" | "R" | "I"): string {
  return p === "D" ? "text-blue-600" : p === "R" ? "text-red-600" : "text-amber-600";
}

function partyLabel(p: "D" | "R" | "I"): string {
  return p === "D" ? "Democrat" : p === "R" ? "Republican" : "Independent";
}

export default async function StateMembersPage({
  params,
}: {
  params: Promise<{ state: string }>;
}) {
  const { state } = await params;
  const code = state.toUpperCase();
  const stateName = STATE_NAMES[code];
  if (!stateName) notFound();

  const [allSenators, allHouse, feed, bioguides] = await Promise.all([
    getSenators(),
    getHouseMembers(),
    getFeed({ perPage: 20, state: code, roster: "us-congress" }),
    sql`SELECT id, bioguide_id FROM officials WHERE bioguide_id IS NOT NULL AND state = ${code}`,
  ]);

  const senators = allSenators.filter((s) => s.state === code);
  const houseMembers = allHouse
    .filter((m) => m.state === code)
    .sort((a, b) => {
      const aN = Number(a.district);
      const bN = Number(b.district);
      if (Number.isFinite(aN) && Number.isFinite(bN)) return aN - bN;
      return (a.district ?? "").localeCompare(b.district ?? "");
    });

  if (senators.length === 0 && houseMembers.length === 0) notFound();

  const bioMap = new Map<string, string>();
  for (const row of bioguides as { id: string; bioguide_id: string }[]) {
    bioMap.set(row.id, row.bioguide_id);
  }

  const totalReleases =
    senators.reduce((s, m) => s + m.release_count, 0) +
    houseMembers.reduce((s, m) => s + m.release_count, 0);

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-2">
        <Link href="/members" className="hover:text-neutral-900">
          Members
        </Link>{" "}
        / {stateName}
      </p>
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        {stateName} delegation
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-2 max-w-2xl">
        {senators.length} senator{senators.length === 1 ? "" : "s"} and{" "}
        {houseMembers.length} U.S. House member
        {houseMembers.length === 1 ? "" : "s"} representing {stateName}.{" "}
        {totalReleases.toLocaleString()} releases archived since January 2025.
      </p>
      <p className="text-xs text-neutral-500 leading-relaxed mb-10 max-w-2xl">
        <Link
          href={`/feed?state=${code}`}
          className="underline hover:text-neutral-900"
        >
          Open the full state feed →
        </Link>
      </p>

      {senators.length > 0 && (
        <section className="mb-12">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
            Senators
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {senators.map((s) => (
              <MemberCard
                key={s.id}
                member={s}
                href={`/senators/${s.id}`}
                photoSrc={bioMap.get(s.id) ? `/senators/${bioMap.get(s.id)}.jpg` : null}
                subline={`Sen. · ${partyLabel(s.party)}`}
              />
            ))}
          </div>
        </section>
      )}

      {houseMembers.length > 0 && (
        <section className="mb-12">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4">
            U.S. House
          </h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {houseMembers.map((m) => (
              <MemberCard
                key={m.id}
                member={m}
                href={`/house/${m.id}`}
                photoSrc={bioMap.get(m.id) ? `/house/${bioMap.get(m.id)}.jpg` : null}
                subline={`${formatDistrict(m.district)} · ${partyLabel(m.party)}`}
              />
            ))}
          </div>
        </section>
      )}

      <section className="mb-12">
        <div className="flex items-baseline justify-between border-b border-neutral-900 pb-2 mb-4">
          <h2 className="text-xs uppercase tracking-wider text-neutral-500">
            Recent releases
          </h2>
          {feed.total > feed.items.length && (
            <Link
              href={`/feed?state=${code}`}
              className="text-xs text-neutral-500 hover:text-neutral-900 underline"
            >
              See all {feed.total.toLocaleString()}
            </Link>
          )}
        </div>
        {feed.items.length === 0 ? (
          <p className="text-sm text-neutral-500">
            No releases yet from this delegation.
          </p>
        ) : (
          <div className="space-y-4">
            {feed.items.map((item) => (
              <ReleaseCard key={item.id} item={item} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function MemberCard({
  member,
  href,
  photoSrc,
  subline,
}: {
  member: SenatorWithCount;
  href: string;
  photoSrc: string | null;
  subline: string;
}) {
  return (
    <Link
      href={href}
      className="flex items-center gap-3 border border-neutral-200 rounded-md p-3 hover:border-neutral-900 transition-colors group"
    >
      {photoSrc ? (
        <Image
          src={photoSrc}
          alt={member.full_name}
          width={48}
          height={48}
          className="size-12 object-cover object-top rounded-sm"
          unoptimized
        />
      ) : (
        <div className="size-12 bg-neutral-200 flex items-center justify-center text-xs text-neutral-500 rounded-sm">
          {member.full_name.split(" ").map((n) => n[0]).join("").slice(0, 2)}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-sm text-neutral-900 font-medium group-hover:underline truncate">
          {member.full_name}
        </p>
        <p className={`text-xs ${partyClass(member.party)} truncate`}>
          {subline}
        </p>
        <p className="text-[11px] text-neutral-500 font-[family-name:var(--font-dm-mono)] tabular-nums">
          {member.release_count > 0
            ? `${member.release_count.toLocaleString()} releases`
            : "no releases yet"}
          {member.latest_release && (
            <span className="text-neutral-300">
              {" · "}
              {formatMonthYear(member.latest_release)}
            </span>
          )}
        </p>
      </div>
    </Link>
  );
}
