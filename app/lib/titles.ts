// Title normalization for press release headlines.
// Released titles often arrive ALL CAPS or with raw HTML entities; this brings
// them to a consistent display form.

const SMALL_WORDS = new Set([
  "a","an","the","and","but","or","for","nor","on","at","to","by","of","in","is","it","as","with",
]);

// Tokens that stay uppercase when an ALL CAPS headline is title-cased.
// This replaced a length rule ("keep any 2-4 letter caps token") that kept
// LAS and WITH shouting while lowercasing HOUSE, which produced headlines
// like `Leader Jeffries in LAS Vegas: "house Democrats ... WITH Labor"`.
// Only real acronyms belong here.
const ACRONYMS = new Set([
  "US","USA","DC","AI","ICYMI","GOP","NATO","UN","EU",
  "FBI","DOJ","ICE","EPA","VA","NASA","NIH","CDC","FEMA","IRS","FDA","DHS",
  "DOD","DOE","HHS","HUD","TSA","CIA","NSA","SEC","FTC","FCC","USDA","NOAA",
  "CBO","GAO","ATF","DEA","CBP","USCIS","NTSB","OSHA","FAA","FERC","USPS",
  "SSA","SBA","FAFSA","NDAA","COVID","AAPI","LGBTQ","STEM","PFAS","SNAP",
  "VAWA","HBCU","ROTC","UAW","GDP","CEO","PPE","EV","POW","MIA","AG","NIL",
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
  rsquo: "’",
  lsquo: "‘",
  rdquo: "”",
  ldquo: "“",
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

// Title-case one whitespace-delimited token, capitalizing the first letter of
// each letter run so leading punctuation (`"HOUSE`, `(SENATE)`) and hyphenated
// compounds survive. A one-letter run after an apostrophe stays lowercase so
// possessives read `Congress's`, not `Congress'S`.
function titleCaseToken(token: string): string {
  return token
    .toLowerCase()
    .replace(/[a-z]+/g, (run, offset: number, whole: string) => {
      if (offset > 0 && whole[offset - 1] === "'" && run.length === 1) return run;
      return run.charAt(0).toUpperCase() + run.slice(1);
    });
}

// A small word keeps its capital at the start of the title and after any
// terminal or opening punctuation — `Vegas: "House ...`, not `Vegas: "house`.
function isSentenceStart(text: string, offset: number): boolean {
  for (let i = offset - 1; i >= 0; i--) {
    const ch = text[i];
    if (/\s/.test(ch)) continue;
    return /[:;.!?—–"'“‘([]/.test(ch);
  }
  return true;
}

export function normalizeTitle(title: string): string {
  const decoded = decodeEntities(title);
  const letters = decoded.replace(/[^a-zA-Z]/g, "");
  if (letters.length === 0) return decoded;
  const upperCount = letters.replace(/[^A-Z]/g, "").length;
  if (upperCount / letters.length < 0.7) return decoded;

  return decoded.replace(/\S+/g, (word, offset: number) => {
    const core = word.replace(/[^a-zA-Z]/g, "");
    if (core.length > 0 && ACRONYMS.has(core.toUpperCase())) {
      return word.toUpperCase();
    }
    if (!isSentenceStart(decoded, offset) && SMALL_WORDS.has(core.toLowerCase())) {
      return word.toLowerCase();
    }
    return titleCaseToken(word);
  });
}
