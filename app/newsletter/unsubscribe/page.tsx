const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export const metadata = {
  title: "Unsubscribe · Capitol Releases",
  description: "Confirm that you want to unsubscribe from the Capitol Releases daily brief.",
};

export default async function UnsubscribePage({
  searchParams,
}: {
  searchParams: Promise<{ token?: string }>;
}) {
  const { token = "" } = await searchParams;
  const valid = UUID_RE.test(token);

  return (
    <main className="mx-auto max-w-lg px-5 py-16 text-neutral-900">
      <h1 className="mb-4 font-serif text-3xl">Unsubscribe from Capitol Releases?</h1>
      {valid ? (
        <>
          <p className="mb-6 leading-7 text-neutral-600">
            Submit this form to stop receiving the daily brief.
          </p>
          <form method="post" action={`/api/newsletter/unsubscribe?token=${token}`}>
            <button
              type="submit"
              className="bg-neutral-900 px-4 py-2 text-sm font-medium text-white hover:bg-neutral-700"
            >
              Unsubscribe
            </button>
          </form>
        </>
      ) : (
        <p className="leading-7 text-neutral-600">This unsubscribe link is invalid.</p>
      )}
    </main>
  );
}
