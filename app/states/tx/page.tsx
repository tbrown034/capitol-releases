import Link from "next/link";

export const metadata = {
  title: "Texas Senate — Capitol Releases",
};

export const revalidate = 600;

export default async function TexasStatePage() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <Link
        href="/states"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← All states
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        Texas Senate
      </h1>
      <p className="text-sm text-neutral-600 leading-relaxed mb-6 max-w-2xl">
        31 members. Republican majority. Lieutenant Governor Dan Patrick
        presides. Convenes in odd-numbered years for the regular biennial
        session, plus called special sessions.
      </p>

      <div className="border border-amber-200 bg-amber-50 px-4 py-3 mb-8 max-w-2xl">
        <p className="text-xs uppercase tracking-wider text-amber-900 mb-1 font-medium">
          Backfill in progress
        </p>
        <p className="text-sm text-amber-900 leading-relaxed">
          We&apos;re collecting every press release from each TX senator&apos;s
          official site, going back to January 1, 2025. The full archive will
          appear here when ingest completes.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-10 max-w-2xl">
        <Stat label="Senators" value="31" />
        <Stat label="Republican" value="20" />
        <Stat label="Democrat" value="11" />
        <Stat label="Backfill since" value="Jan 2025" />
      </div>

      <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-4">
        What you&apos;ll find here
      </h2>
      <ul className="text-sm text-neutral-700 leading-relaxed space-y-2 max-w-2xl">
        <li>
          Every press release, statement, op-ed and floor statement from each
          TX senator&apos;s official site, with publication date and source URL.
        </li>
        <li>
          Daily ingest. Provenance on every record. Deletion detection — if a
          senator removes a release, we keep the tombstone.
        </li>
        <li>
          Search across all 31 senators, filter by topic, follow individual
          senators&apos; publishing cadence over time.
        </li>
      </ul>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs uppercase tracking-wider text-neutral-400 mb-1">
        {label}
      </p>
      <p className="text-2xl font-[family-name:var(--font-dm-mono)] tabular-nums text-neutral-900">
        {value}
      </p>
    </div>
  );
}
