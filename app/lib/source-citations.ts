export type CitationSource = {
  item_id: string;
  title: string;
  source_url: string;
  published_at: string | null;
};

export type NumberedSource = Omit<CitationSource, "item_id"> & { n: number };

// Retrieval and validation operate on passages. Reader-facing references
// identify the release, so two cited passages from one release share a number.
export function createSourceCitations() {
  const byItem = new Map<string, number>();
  const sources: NumberedSource[] = [];
  function numberFor(source: CitationSource): number {
    const existing = byItem.get(source.item_id);
    if (existing !== undefined) return existing;
    const n = sources.length + 1;
    byItem.set(source.item_id, n);
    sources.push({
      n,
      title: source.title,
      source_url: source.source_url,
      published_at: source.published_at,
    });
    return n;
  }
  return { sources, numberFor };
}
