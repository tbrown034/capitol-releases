import Link from "next/link";
import { getSenators } from "../lib/queries";
import { PartyBadge } from "../components/party-badge";
import type { SenatorWithCount } from "../lib/db";

export const metadata = {
  title: "Senators -- Capitol Releases",
};

export default async function SenatorsPage() {
  const senators = await getSenators();

  const withReleases = senators.filter((s) => s.release_count > 0);
  const withoutReleases = senators.filter((s) => s.release_count === 0);

  return (
    <div className="mx-auto max-w-5xl px-4 py-8">
      <h1 className="text-2xl font-bold">Senators</h1>
      <p className="mt-1 text-sm text-gray-500">
        All 100 senators with press release counts.{" "}
        {withReleases.length} have scraped releases so far.
      </p>

      <div className="mt-6 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs uppercase tracking-wide text-gray-500">
              <th className="pb-2 pr-4">Senator</th>
              <th className="pb-2 pr-4">Party</th>
              <th className="pb-2 pr-4">State</th>
              <th className="pb-2 pr-4 text-right">Releases</th>
              <th className="pb-2 text-right">Latest</th>
            </tr>
          </thead>
          <tbody>
            {senators.map((s: SenatorWithCount) => (
              <tr
                key={s.id}
                className="border-b border-gray-50 hover:bg-gray-50"
              >
                <td className="py-2.5 pr-4">
                  <Link
                    href={`/senators/${s.id}`}
                    className="font-medium text-gray-900 hover:text-blue-600"
                  >
                    {s.full_name}
                  </Link>
                </td>
                <td className="py-2.5 pr-4">
                  <PartyBadge party={s.party} />
                </td>
                <td className="py-2.5 pr-4 text-gray-600">{s.state}</td>
                <td className="py-2.5 pr-4 text-right tabular-nums font-medium">
                  {s.release_count > 0 ? s.release_count : (
                    <span className="text-gray-300">--</span>
                  )}
                </td>
                <td className="py-2.5 text-right text-gray-500">
                  {s.latest_release
                    ? new Date(s.latest_release).toLocaleDateString("en-US", {
                        month: "short",
                        day: "numeric",
                      })
                    : "--"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {withoutReleases.length > 0 && (
        <p className="mt-4 text-xs text-gray-400">
          {withoutReleases.length} senators pending backfill.
        </p>
      )}
    </div>
  );
}
