import Link from "next/link";

export const metadata = {
  title: "Bluesky — Capitol Releases",
  description:
    "Real-time archive of every senator's Bluesky posts, with the same provenance and deletion detection as press releases.",
};

export const revalidate = 3600;

export default function BlueskyPage() {
  return (
    <div className="mx-auto max-w-5xl px-4">
      <section className="pt-8 pb-6 md:pt-10 md:pb-8">
        <p className="text-[11px] uppercase tracking-wider text-neutral-500 mb-2">
          Coming Soon
        </p>
        <h1 className="font-serif text-4xl sm:text-5xl md:text-[3.25rem] leading-[1.05] text-neutral-900 mb-3 md:mb-4">
          Bluesky for the
          <br />
          Senate.
        </h1>
        <p className="text-base md:text-lg text-neutral-700 max-w-2xl leading-snug mb-3">
          Every senator&rsquo;s Bluesky posts &mdash; archived in real time,
          with deletion detection, the same way we archive press releases.
        </p>
        <p className="text-sm md:text-base text-neutral-500 max-w-2xl leading-relaxed">
          Twitter is no longer a usable source. Bluesky is where official
          accounts are migrating. The AT Protocol Jetstream is a public
          firehose &mdash; we tap it, attribute each post to a verified senator
          handle, and store with the same archival permanence the corpus
          already runs on.
        </p>
      </section>

      <section className="mb-12 md:mb-16">
        <div className="border border-amber-200 bg-amber-50 rounded-md px-5 py-4 max-w-2xl">
          <p className="text-[11px] uppercase tracking-wider text-amber-900 mb-1.5 font-semibold">
            In development
          </p>
          <p className="text-sm text-amber-900 leading-relaxed mb-2">
            Handle directory in recon. Collector in development. Schema landing
            with the next migration.
          </p>
          <p className="text-xs text-amber-900/80 leading-relaxed">
            We&rsquo;re committing to verified handles only &mdash; no parody
            accounts, no campaign-side, no staffer reposts. Each handle is
            confirmed against the senator&rsquo;s official site or DID
            registry before it lands in the index.
          </p>
        </div>
      </section>

      <section className="mb-12 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          Why Bluesky
        </h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 md:gap-8">
          <Pillar
            title="The successor venue"
            body="Twitter/X has degraded as a public archive — paywalls, API closures, deletions without record. Bluesky is where senators, agencies, and journalists are rebuilding the wire."
          />
          <Pillar
            title="The protocol matters"
            body="AT Protocol publishes a public firehose. Every post, every delete, every edit is broadcast as a structured event. Archival becomes a streaming problem, not a scraping one."
          />
          <Pillar
            title="Deletes are events"
            body="Unlike Twitter, where a delete is a silent removal, Bluesky broadcasts the deletion. We catch it, tombstone the post, and keep the original — the same permanence press releases get."
          />
        </div>
      </section>

      <section className="mb-12 md:mb-16">
        <h2 className="text-xs uppercase tracking-wider text-neutral-500 border-b border-neutral-900 pb-2 mb-4 md:mb-6">
          What you&rsquo;ll find here
        </h2>
        <ul className="space-y-3 max-w-2xl">
          <Bullet>
            Every post from every verified senator&rsquo;s Bluesky account,
            ingested in real time off the AT Protocol Jetstream.
          </Bullet>
          <Bullet>
            Threads reconstructed in publication order, with reply chains
            attributed to the senator&rsquo;s own handle.
          </Bullet>
          <Bullet>
            Deletion detection. If a senator removes a post, the tombstone
            stays &mdash; with the original text, the timestamp, and the
            firehose event that recorded the deletion.
          </Bullet>
          <Bullet>
            Cross-stream search. Find every time a senator said something on
            Bluesky and then said it again in a press release, or vice versa.
          </Bullet>
          <Bullet>
            Full provenance per post: the AT URI, the CID, the firehose seq,
            the senator handle&rsquo;s DID. Citable, deterministic, archival.
          </Bullet>
        </ul>
      </section>

      <section className="mb-16">
        <div className="border-t border-neutral-200 pt-8">
          <p className="text-xs text-neutral-500 max-w-2xl leading-relaxed">
            Status updates land in{" "}
            <Link href="/about" className="underline hover:text-neutral-900">
              the methodology page
            </Link>{" "}
            as the firehose comes online. Every senator&rsquo;s page will gain
            a Bluesky tab once their handle is verified and indexed.
          </p>
        </div>
      </section>
    </div>
  );
}

function Pillar({ title, body }: { title: string; body: string }) {
  return (
    <div>
      <h3 className="font-serif text-lg text-neutral-900 mb-2 leading-tight">
        {title}
      </h3>
      <p className="text-sm text-neutral-600 leading-relaxed">{body}</p>
    </div>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-3 text-sm text-neutral-700 leading-relaxed">
      <span className="mt-2 inline-block h-1 w-1 shrink-0 rounded-full bg-neutral-400" />
      <span>{children}</span>
    </li>
  );
}
