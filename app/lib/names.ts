const SUFFIXES = new Set(["Jr.", "Sr.", "Jr", "Sr", "II", "III", "IV"]);

export function familyName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).map((p) => p.replace(/,$/, ""));
  if (parts.length === 0) return fullName;
  const last = parts[parts.length - 1];
  if (SUFFIXES.has(last) && parts.length >= 2) {
    return parts[parts.length - 2];
  }
  return last;
}

// Common political nicknames. Senators often refer to themselves by a nickname
// in body copy ("Chuck", "Bill") even when the database has the formal name
// ("Charles E. Schumer", "William Cassidy"). Without this expansion, the
// nickname leaks into "topics they own" because the exclusion list only sees
// the formal name tokens.
const NICKNAMES: Record<string, string[]> = {
  charles: ["chuck", "charlie"],
  william: ["bill", "will", "willie"],
  robert: ["bob", "rob", "robbie"],
  richard: ["rick", "dick", "richie"],
  michael: ["mike", "mikey"],
  timothy: ["tim", "timmy"],
  thomas: ["tom", "tommy"],
  edward: ["ed", "ted", "eddie"],
  theodore: ["ted", "teddy"],
  james: ["jim", "jimmy", "jamie"],
  patricia: ["pat", "patty", "trish"],
  patrick: ["pat", "paddy"],
  catherine: ["cathy", "kate", "katie", "cat"],
  katherine: ["kate", "kathy", "katie"],
  elizabeth: ["liz", "beth", "betty", "ellie"],
  margaret: ["maggie", "meg", "peggy"],
  joseph: ["joe", "joey"],
  joshua: ["josh"],
  benjamin: ["ben", "benji"],
  alexander: ["alex"],
  christopher: ["chris", "kit"],
  daniel: ["dan", "danny"],
  raphael: ["raph"],
  cynthia: ["cindy"],
  martin: ["marty"],
  mitchell: ["mitch"],
  ronald: ["ron"],
  donald: ["don", "donny"],
  cornelius: ["neil"],
  cory: ["corey"],
  bernard: ["bernie"],
  angus: ["gus"],
};

const REVERSE_NICKNAMES: Record<string, string[]> = (() => {
  const out: Record<string, string[]> = {};
  for (const [formal, nicks] of Object.entries(NICKNAMES)) {
    for (const n of nicks) {
      out[n] = (out[n] ?? []).concat(formal);
    }
  }
  return out;
})();

/** Tokens to exclude when mining a senator's signature topics. Includes
 *  formal-name parts (split, lower, dropping initials), known nicknames for
 *  each part, and the senator-id slug parts. */
export function excludeNameTokens(fullName: string, senatorId: string): string[] {
  const tokens = new Set<string>();
  const fromName = fullName
    .toLowerCase()
    .split(/[^a-z]+/)
    .filter((t) => t.length > 1);
  for (const t of fromName) tokens.add(t);
  for (const t of senatorId.toLowerCase().split(/[^a-z]+/)) {
    if (t.length > 1) tokens.add(t);
  }
  // Expand each token with its nicknames (Charles -> chuck) and formals (chuck -> charles).
  for (const t of Array.from(tokens)) {
    for (const n of NICKNAMES[t] ?? []) tokens.add(n);
    for (const f of REVERSE_NICKNAMES[t] ?? []) tokens.add(f);
  }
  // Drop tokens shorter than 3 chars (matches getSenatorSignatureTopics filter).
  return Array.from(tokens).filter((t) => t.length > 2);
}
