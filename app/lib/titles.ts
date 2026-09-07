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
// Matching runs per letter-group, so FBI'S and NATO-LED keep the acronym.
const ACRONYMS = new Set([
  "US","USA","DC","AI","ICYMI","GOP","NATO","UN","EU","PBS","NPR",
  "FBI","DOJ","ICE","EPA","VA","NASA","NIH","CDC","FEMA","IRS","FDA","DHS",
  "DOD","DOE","HHS","HUD","TSA","CIA","NSA","SEC","FTC","FCC","USDA","NOAA",
  "CBO","GAO","ATF","DEA","CBP","USCIS","NTSB","OSHA","FAA","FERC","USPS",
  "SSA","SSI","SBA","FAFSA","NDAA","COVID","AAPI","LGBTQ","STEM","PFAS",
  "SNAP","WIC","VAWA","HBCU","ROTC","UAW","GDP","CEO","PPE","EV","POW","MIA",
  "AG","NIL","DACA","ACA","IVF","USMCA","NAFTA","MAGA",
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

// Title-case one whitespace-delimited token, letter run by letter run, so
// leading punctuation (`"HOUSE`, `(SENATE)`), hyphenated compounds and
// possessives all survive. A run that is a known acronym stays uppercase, so
// FBI'S reads FBI's and NATO-LED reads NATO-Led. A one-letter run after an
// apostrophe, straight or curly, stays lowercase: Congress's, not Congress'S.
function titleCaseToken(token: string): string {
  return token.replace(/[a-zA-Z]+/g, (run, offset: number, whole: string) => {
    if (ACRONYMS.has(run.toUpperCase())) return run.toUpperCase();
    const prev = offset > 0 ? whole[offset - 1] : "";
    if ((prev === "'" || prev === "\u2019") && run.length === 1) {
      return run.toLowerCase();
    }
    return run.charAt(0).toUpperCase() + run.slice(1).toLowerCase();
  });
}

// Opening punctuation that starts a fresh phrase, so the next word keeps its
// capital even when it is a small word: `Vegas: "House ...`, `Says "In ...`.
const OPENING_PUNCTUATION = /["'\u2018\u2019\u201c\u201d([]/;

// A small word keeps its capital at the start of the title, after terminal or
// opening punctuation in an earlier token, and after opening punctuation
// carried inside its own token (SAYS \u201cIN THIS BILL\u201d).
function isPhraseStart(text: string, offset: number, word: string): boolean {
  const firstLetter = word.search(/[a-zA-Z]/);
  if (firstLetter > 0 && OPENING_PUNCTUATION.test(word.slice(0, firstLetter))) {
    return true;
  }
  for (let i = offset - 1; i >= 0; i--) {
    const ch = text[i];
    if (/\s/.test(ch)) continue;
    return /[:;.!?\u2014\u2013]/.test(ch) || OPENING_PUNCTUATION.test(ch);
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
    // Whole-token check first, so dotted forms like U.S. stay uppercase even
    // though neither of their letter runs is an acronym on its own.
    const core = word.replace(/[^a-zA-Z]/g, "");
    if (core.length > 0 && ACRONYMS.has(core.toUpperCase())) {
      return word.toUpperCase();
    }
    if (
      !isPhraseStart(decoded, offset, word) &&
      SMALL_WORDS.has(core.toLowerCase())
    ) {
      return word.toLowerCase();
    }
    return titleCaseToken(word);
  });
}
