import Link from "next/link";
import Image from "next/image";
import { getSenators } from "../lib/queries";
import { sql } from "../lib/db";
import type { SenatorWithCount } from "../lib/db";

export const metadata = {
  title: "Directory -- Capitol Releases",
};

export const dynamic = "force-dynamic";

export default async function SenatorsPage() {
  const senators = await getSenators();

  // Get bioguide IDs for photos
  const bioguides = await sql`SELECT id, bioguide_id FROM senators WHERE bioguide_id IS NOT NULL`;
  const bioMap = new Map<string, string>();
  for (const row of bioguides as { id: string; bioguide_id: string }[]) {
    bioMap.set(row.id, row.bioguide_id);
  }

  const withReleases = senators.filter((s) => s.release_count > 0);

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-1">
        Senator Directory
      </h1>
      <p className="text-sm text-neutral-500 mb-8">
        {withReleases.length} senators with archived press releases.
        Photos from the Congressional Bioguide.
      </p>

      <div className="border-b border-neutral-200 mb-8" />

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-neutral-800 text-xs uppercase tracking-wider text-neutral-500">
            <th className="pb-2 pr-4 text-left font-medium">Senator</th>
            <th className="pb-2 pr-4 text-left font-medium">State</th>
            <th className="pb-2 pr-4 text-left font-medium">Party</th>
            <th className="pb-2 pr-4 text-right font-medium">Releases</th>
            <th className="pb-2 text-right font-medium">Latest</th>
          </tr>
        </thead>
        <tbody>
          {senators.map((s: SenatorWithCount, i: number) => {
            const bioId = bioMap.get(s.id);
            return (
              <tr
                key={s.id}
                className={`border-b border-neutral-100 ${i % 2 === 1 ? "bg-neutral-50/60" : ""}`}
              >
                <td className="py-2.5 pr-4">
                  <Link
                    href={`/senators/${s.id}`}
                    className="flex items-center gap-3 hover:underline"
                  >
                    {bioId ? (
                      <Image
                        src={`/senators/${bioId}.jpg`}
                        alt={s.full_name}
                        width={32}
                        height={32}
                        className="h-8 w-8 object-cover object-top"
                        unoptimized
                      />
                    ) : (
                      <div className="h-8 w-8 bg-neutral-200 flex items-center justify-center text-[10px] text-neutral-400">
                        {s.full_name.split(" ").map(n => n[0]).join("").slice(0, 2)}
                      </div>
                    )}
                    <span className="text-neutral-900 font-medium">{s.full_name}</span>
                  </Link>
                </td>
                <td className="py-2.5 pr-4 text-neutral-500">{s.state}</td>
                <td className="py-2.5 pr-4">
                  <span className={`${
                    s.party === "D" ? "text-blue-600" : s.party === "R" ? "text-red-600" : "text-amber-600"
                  }`}>
                    {s.party === "D" ? "Democrat" : s.party === "R" ? "Republican" : "Independent"}
                  </span>
                </td>
                <td className="py-2.5 pr-4 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-600">
                  {s.release_count > 0 ? s.release_count : (
                    <span className="text-neutral-300">---</span>
                  )}
                </td>
                <td className="py-2.5 text-right font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-400 whitespace-nowrap">
                  {s.latest_release
                    ? new Date(s.latest_release).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })
                    : "---"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
