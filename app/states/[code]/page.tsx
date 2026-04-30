import Link from "next/link";
import { notFound, redirect } from "next/navigation";
import { STATE_NAMES } from "../../lib/states";
import { getStateRow } from "../../lib/state-coverage";

export const revalidate = 3600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const upper = code.toUpperCase();
  const name = STATE_NAMES[upper];
  if (!name) return { title: "State not found — Capitol Releases" };
  return { title: `${name} — Capitol Releases` };
}

export default async function StateCodePage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const upper = code.toUpperCase();
  const name = STATE_NAMES[upper];
  if (!name) notFound();

  const row = getStateRow(upper);

  // If the state has its own dedicated page (e.g. /texas), defer to it.
  // The catch-all only handles planned states and unrecognized-but-valid codes.
  if (row?.href && row.href !== `/states/${code.toLowerCase()}`) {
    redirect(row.href);
  }

  const isPlanned = row?.status === "planned";

  return (
    <div className="mx-auto max-w-5xl px-4 py-12">
      <Link
        href="/states"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← All states
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900 mb-3">
        {name}
      </h1>

      {isPlanned ? (
        <>
          <p className="text-sm text-neutral-600 leading-relaxed mb-6 max-w-2xl">
            {name} is on the Phase 1 roadmap. We&apos;re shipping Texas first as
            the pilot, then bringing the same archival method &mdash;
            provenance, daily ingest, deletion detection &mdash; to {name} and
            the rest of the planned slate.
          </p>

          <div className="border border-neutral-200 px-4 py-3 mb-8 max-w-2xl">
            <p className="text-xs uppercase tracking-wider text-neutral-500 mb-1 font-medium">
              Planned
            </p>
            <p className="text-sm text-neutral-700 leading-relaxed">
              {row.chamber} &middot;{" "}
              <span className="font-[family-name:var(--font-dm-mono)] tabular-nums">
                {row.members}
              </span>{" "}
              members. Coverage horizon: January 1, 2025 forward, matching the
              U.S. Senate corpus.
            </p>
          </div>

          <h2 className="text-xs uppercase tracking-wider text-neutral-500 mb-3">
            Why we&apos;re not live yet
          </h2>
          <ul className="text-sm text-neutral-700 leading-relaxed space-y-2 max-w-2xl mb-8">
            <li>
              State legislatures publish on a long tail of platforms &mdash;
              party caucus sites, member sites, joint chamber feeds. Each needs
              recon and a tuned collector before we can promise near-complete
              coverage.
            </li>
            <li>
              We&apos;re prioritizing depth over breadth. Texas first, verified,
              before opening the next state. {name} follows in the same
              archival shape.
            </li>
          </ul>

          <Link
            href="/texas"
            className="inline-flex items-center gap-2 text-sm text-neutral-900 hover:underline"
          >
            See the Texas pilot →
          </Link>
        </>
      ) : (
        <>
          <p className="text-sm text-neutral-600 leading-relaxed mb-6 max-w-2xl">
            {name} is not on the current roadmap. The U.S. Senate corpus
            (already live) covers both of {name}&apos;s federal senators
            &mdash; browse them in the directory.
          </p>

          <div className="flex flex-wrap gap-3 mb-8">
            <Link
              href={`/senators?state=${upper}`}
              className="text-sm text-neutral-900 underline hover:no-underline"
            >
              {name} U.S. senators →
            </Link>
            <Link
              href="/texas"
              className="text-sm text-neutral-900 underline hover:no-underline"
            >
              See the Texas pilot →
            </Link>
            <Link
              href="/states"
              className="text-sm text-neutral-900 underline hover:no-underline"
            >
              All states →
            </Link>
          </div>

          <p className="text-xs text-neutral-500 leading-relaxed max-w-2xl">
            State legislature coverage rolls out in waves. Texas is the pilot;
            California, New York, and Ohio are next. Want {name} prioritized?
            That&apos;s exactly the kind of signal we&apos;re looking for.
          </p>
        </>
      )}
    </div>
  );
}
