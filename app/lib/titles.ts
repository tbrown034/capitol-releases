// Title normalization for press release headlines.
// Released titles often arrive ALL CAPS or with raw HTML entities; this brings
// them to a consistent display form.

const SMALL_WORDS = new Set([
  "a","an","the","and","but","or","for","nor","on","at","to","by","of","in","is","it","as",
]);

const NAMED_ENTITIES: Record<string, string> = {
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
  nbsp: " ",
  ndash: "–",
  mdash: "—",
  hellip: "…",
  rsquo: "\u2019",
  lsquo: "\u2018",
  rdquo: "\u201d",
  ldquo: "\u201c",
};

function decodeEntities(s: string): string {
  // Numeric entities: &#39; &#x2019; — including the broken `&x2019;`
  // form some sites emit (missing the leading #).
  return s
    .replace(/&#x([0-9a-fA-F]+);?/g, (_, hex) =>
      String.fromCodePoint(parseInt(hex, 16))
    )
    .replace(/&#(\d+);?/g, (_, dec) => String.fromCodePoint(parseInt(dec, 10)))
    .replace(/&x([0-9a-fA-F]+);?/g, (_, hex) =>
      String.fromCodePoint(parseInt(hex, 16))
    )
    .replace(/&([a-zA-Z]+);/g, (m, name) => NAMED_ENTITIES[name] ?? m);
}

export function normalizeTitle(title: string): string {
  const decoded = decodeEntities(title);
  const letters = decoded.replace(/[^a-zA-Z]/g, "");
  if (letters.length === 0) return decoded;
  const upperCount = letters.replace(/[^A-Z]/g, "").length;
  if (upperCount / letters.length < 0.7) return decoded;

  return decoded.replace(/\S+/g, (word, offset: number) => {
    const core = word.replace(/[^a-zA-Z]/g, "");
    if (/^[A-Z]{2,4}$/.test(core) && !SMALL_WORDS.has(core.toLowerCase()))
      return word;
    if (offset > 0 && SMALL_WORDS.has(core.toLowerCase()))
      return word.toLowerCase();
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  });
}
