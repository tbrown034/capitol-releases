import Link from "next/link";
import { notFound } from "next/navigation";
import {
  getColoradoLegislator,
  getReleasesMentioning,
} from "../../lib/colorado";
import { ReleaseCard } from "../../components/release-card";

export const revalidate = 600;

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const legislator = await getColoradoLegislator(id);
  if (!legislator) return { title: "Not found — Capitol Releases" };
  const seat = `${legislator.chamber === "senate" ? "Senate District" : "House District"} ${legislator.district}`;
  return {
    title: `${legislator.full_name} — Colorado — Capitol Releases`,
    description: `Caucus releases naming ${legislator.full_name} (${legislator.party}), ${seat}.`,
  };
}

export default async function ColoradoLegislatorPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const legislator = await getColoradoLegislator(id);
  if (!legislator) notFound();

  // Quoted first, then the rest. A member's own quotes are the material a
  // reporter is looking for; sponsor-list appearances are context.
  const [quotedItems, allItems] = await Promise.all([
    getReleasesMentioning(id, "quoted", 40),
    getReleasesMentioning(id, undefined, 60),
  ]);
  const quotedIds = new Set(quotedItems.map((i) => i.id));
  const otherItems = allItems.filter((i) => !quotedIds.has(i.id));

  const seatLabel = `${legislator.chamber === "senate" ? "Senate District" : "House District"} ${legislator.district}`;

  return (
    <div className="mx-auto max-w-3xl px-4 py-12">
      <Link
        href="/colorado"
        className="text-xs text-neutral-500 hover:text-neutral-900 mb-6 inline-block"
      >
        ← Colorado
      </Link>

      <h1 className="font-[family-name:var(--font-source-serif)] text-4xl text-neutral-900">
        {legislator.full_name}
      </h1>
      <p className="mt-1 text-sm text-neutral-500">
        {legislator.party === "D"
          ? "Democrat"
          : legislator.party === "R"
            ? "Republican"
            : legislator.party}{" "}
        · {seatLabel} · Colorado General Assembly
      </p>

      {legislator.official_url && (
        <a
          href={legislator.official_url}
          target="_blank"
          rel="noopener noreferrer"
          className="mt-2 inline-block text-xs text-neutral-500 hover:text-neutral-900 underline"
        >
          Official biography page
          <span aria-hidden> ↗</span>
        </a>
      )}

      <div className="mt-6 rounded-none border-l-2 border-amber-200 bg-amber-50/50 px-3 py-2">
        <p className="text-[12px] text-neutral-700 leading-relaxed">
          {legislator.full_name} does not publish a press page. Colorado
          legislators have no per-member pressroom, so every release below was
          published by a party caucus and names them in its text.
        </p>
      </div>

      <dl className="mt-6 flex gap-8">
        <div>
          <dt className="text-[10px] uppercase tracking-wider text-neutral-400">
            Quoted in
          </dt>
          <dd className="font-[family-name:var(--font-dm-mono)] text-2xl text-neutral-900 tabular-nums">
            {legislator.quoted_count}
          </dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wider text-neutral-400">
            Named without a quote
          </dt>
          <dd className="font-[family-name:var(--font-dm-mono)] text-2xl text-neutral-900 tabular-nums">
            {legislator.mentioned_count}
          </dd>
        </div>
      </dl>

      {quotedItems.length > 0 && (
        <>
          <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mt-10 mb-1">
            Quoted
          </h2>
          <p className="text-xs text-neutral-500 mb-3">
            Releases carrying a direct quotation from {legislator.full_name}.
          </p>
          <div>
            {quotedItems.map((item) => (
              <ReleaseCard key={item.id} item={item} />
            ))}
          </div>
        </>
      )}

      {otherItems.length > 0 && (
        <>
          <h2 className="font-[family-name:var(--font-source-serif)] text-2xl text-neutral-900 mt-10 mb-1">
            Also named
          </h2>
          <p className="text-xs text-neutral-500 mb-3">
            Named in the text — usually as a bill sponsor — without a direct
            quote.
          </p>
          <div>
            {otherItems.map((item) => (
              <ReleaseCard key={item.id} item={item} />
            ))}
          </div>
        </>
      )}

      {quotedItems.length === 0 && otherItems.length === 0 && (
        <p className="mt-10 text-sm text-neutral-500">
          No collected caucus release names {legislator.full_name} yet.
        </p>
      )}
    </div>
  );
}
