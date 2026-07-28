import Link from "next/link";
import type { ReleaseMention, MentionRole } from "../lib/colorado";

// Caucus releases have no individual byline, so these badges are the only
// place a reader sees which legislators a release actually involves. The
// roles are visually ranked because they are not equivalent: being quoted
// is an editorial choice by the caucus press shop, while being named in a
// sponsor list is close to automatic.
const ROLE_STYLE: Record<MentionRole, string> = {
  primary: "border-neutral-900 bg-neutral-900 text-white",
  quoted: "border-neutral-300 bg-white text-neutral-800",
  mentioned: "border-neutral-200 bg-neutral-50 text-neutral-500",
};

const ROLE_TITLE: Record<MentionRole, string> = {
  primary: "Named in the headline",
  quoted: "Directly quoted in this release",
  mentioned: "Named in the body, not quoted",
};

const ROLE_LABEL: Record<MentionRole, string> = {
  primary: "Headlined",
  quoted: "Quoted",
  mentioned: "Mentioned",
};

function seat(chamber: string | null, district: number | null): string {
  if (!chamber || district == null) return "";
  return `${chamber === "senate" ? "SD" : "HD"} ${district}`;
}

export function MentionBadges({
  mentions,
  heading = "Legislators in this release",
}: {
  mentions: ReleaseMention[];
  heading?: string | null;
}) {
  if (mentions.length === 0) return null;

  const groups: MentionRole[] = ["primary", "quoted", "mentioned"];

  return (
    <section className="mt-6 border-t border-neutral-100 pt-4">
      {heading && (
        <h2 className="text-[10px] uppercase tracking-wider text-neutral-400 mb-2">
          {heading}
        </h2>
      )}
      <div className="flex flex-col gap-2">
        {groups.map((role) => {
          const inRole = mentions.filter((m) => m.role === role);
          if (inRole.length === 0) return null;
          return (
            <div key={role} className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] uppercase tracking-wider text-neutral-400 w-[68px] shrink-0">
                {ROLE_LABEL[role]}
              </span>
              {inRole.map((m) => (
                <Link
                  key={`${m.official_id}-${role}`}
                  href={`/colorado/${m.official_id}`}
                  title={`${ROLE_TITLE[role]}${m.matched_text ? ` — "${m.matched_text.slice(0, 140)}"` : ""}`}
                  className={`inline-flex items-center gap-1 border px-1.5 py-0.5 text-[11px] ${ROLE_STYLE[role]} hover:border-neutral-500 transition-colors`}
                >
                  {m.full_name}
                  <span className="opacity-60 font-[family-name:var(--font-dm-mono)]">
                    {m.party}
                    {seat(m.chamber, m.district) && ` ${seat(m.chamber, m.district)}`}
                  </span>
                </Link>
              ))}
            </div>
          );
        })}
      </div>
      <p className="mt-3 text-[10px] text-neutral-400 leading-relaxed">
        Published by the caucus, not by an individual legislator. Names are
        extracted from the release text and matched against the 100-seat
        General Assembly roster.{" "}
        <Link href="/methodology" className="underline hover:text-neutral-600">
          How this works
        </Link>
      </p>
    </section>
  );
}
