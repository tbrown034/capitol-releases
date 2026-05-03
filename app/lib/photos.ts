import bioguideMap from "../../public/senators/bioguide-map.json";

const nameToId = bioguideMap as Record<string, string>;

// Build normalized lookup: lowercase name -> bioguide_id
// Also build last-name based fallback for fuzzy matching
const normalizedMap = new Map<string, string>();
const lastNameMap = new Map<string, string>();

for (const [name, bioguideId] of Object.entries(nameToId)) {
  // Exact match (lowercased)
  normalizedMap.set(name.toLowerCase(), bioguideId);

  // Strip accents for matching
  const stripped = name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  normalizedMap.set(stripped, bioguideId);

  // Last name for fallback
  const parts = name.split(" ");
  const lastName = parts[parts.length - 1].toLowerCase();
  lastNameMap.set(lastName, bioguideId);
}

// Also build official_id -> bioguide_id map
// official_id format: "warren-elizabeth", name format: "Elizabeth Warren"
const idToBioguide = new Map<string, string>();
for (const [name, bioguideId] of Object.entries(nameToId)) {
  const parts = name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .split(/\s+/);

  // Handle multi-word last names: "Cortez Masto" -> "cortez-masto-catherine"
  // Standard: last-first
  if (parts.length === 2) {
    idToBioguide.set(`${parts[1]}-${parts[0]}`, bioguideId);
  } else if (parts.length === 3) {
    // Try "last-first" with middle or compound last name
    idToBioguide.set(`${parts[2]}-${parts[0]}`, bioguideId);
    idToBioguide.set(`${parts[1]}-${parts[2]}-${parts[0]}`, bioguideId);
    // "cortez-masto-catherine" pattern
    idToBioguide.set(`${parts[1]}-${parts[2]}-${parts[0]}`, bioguideId);
  } else if (parts.length >= 4) {
    const first = parts[0];
    const rest = parts.slice(1).join("-");
    idToBioguide.set(`${rest}-${first}`, bioguideId);
  }
}

// Manual overrides for known mismatches between DB names and bioguide map
const ID_OVERRIDES: Record<string, string> = {
  "sanders-bernard": "S000033",  // Bernie vs Bernard
  "king-angus": "K000383",       // Angus King Jr.
  "van-hollen-chris": "V000128",
  "blunt-rochester-lisa": "B001303",
  "cortez-masto-catherine": "C001113",
  "hyde-smith-cindy": "H001079",
  "lujan-ben": "L000570",
  "vance-jd": "V000137",
  "rubio-marco": "R000595",
  "mullin-markwayne": "M001190",
};

for (const [id, bioguideId] of Object.entries(ID_OVERRIDES)) {
  idToBioguide.set(id, bioguideId);
}

export function getSenatorPhotoUrl(fullName: string, officialId?: string): string | null {
  // Non-senate members (e.g. White House) use official_id as the filename directly.
  if (officialId === "whitehouse") return `/senators/whitehouse.jpg`;

  // Texas state senators have IDs like "tx-d29-blanco" and photos stored
  // at /state-senators/tx/dXX.jpg. Pull the district number out of the ID
  // and resolve directly — no bioguide lookup applies.
  if (officialId?.startsWith("tx-d")) {
    const m = officialId.match(/^tx-d(\d{2})-/);
    if (m) return `/state-senators/tx/d${m[1]}.jpg`;
  }

  // Try official_id first (most reliable)
  if (officialId) {
    const byId = idToBioguide.get(officialId);
    if (byId) return `/senators/${byId}.jpg`;
  }

  // Try exact name match
  const lower = fullName.toLowerCase();
  let bioguideId = normalizedMap.get(lower);
  if (bioguideId) return `/senators/${bioguideId}.jpg`;

  // Try stripped accents
  const stripped = fullName
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase();
  bioguideId = normalizedMap.get(stripped);
  if (bioguideId) return `/senators/${bioguideId}.jpg`;

  // Try removing suffixes like "Jr.", "III", "II"
  const noSuffix = stripped.replace(/,?\s*(jr\.?|sr\.?|iii|ii|iv)$/i, "").trim();
  bioguideId = normalizedMap.get(noSuffix);
  if (bioguideId) return `/senators/${bioguideId}.jpg`;

  // Last-name fallback (risky but better than no photo)
  const parts = noSuffix.split(" ");
  const lastName = parts[parts.length - 1];
  bioguideId = lastNameMap.get(lastName);
  if (bioguideId) return `/senators/${bioguideId}.jpg`;

  return null;
}

// Resolve the in-app URL for a senator's archive page based on their ID.
// US senators live under /senators/[id]; Texas state senators live under
// /texas/[id]. Returns the right path regardless of chamber so cards and
// release detail pages don't need chamber-aware logic locally.
export function getSenatorHref(officialId: string): string {
  if (officialId.startsWith("tx-")) return `/texas/${officialId}`;
  return `/senators/${officialId}`;
}

// Resolve a member's headshot URL, chamber-aware.
//   - House member: /house/<bioguide>.jpg (433 of 437 currently shipped)
//   - Senate / executive / TX: existing getSenatorPhotoUrl logic
// Pass `bioguideId` from the DB row when available; we fall back to
// best-effort name lookup if it's missing.
export function getMemberPhotoUrl(
  fullName: string,
  officialId: string,
  chamber: string | null | undefined,
  bioguideId: string | null | undefined
): string | null {
  if (chamber === "house" && bioguideId) {
    return `/house/${bioguideId}.jpg`;
  }
  return getSenatorPhotoUrl(fullName, officialId);
}

// Chamber-aware archive URL: House -> /house/[id], Senate -> /senators/[id],
// TX -> /texas/[id]. Use this when a hero card or feed item could be from
// either chamber.
export function getMemberHref(officialId: string, chamber: string | null | undefined): string {
  if (chamber === "house") return `/house/${officialId}`;
  return getSenatorHref(officialId);
}

// "Sen." / "Rep." byline prefix per chamber. Defaults to "Sen." when the
// chamber is missing — preserves existing rendering for old data.
export function getMemberTitlePrefix(chamber: string | null | undefined): string {
  if (chamber === "house") return "Rep.";
  return "Sen.";
}

export function getInitials(fullName: string): string {
  const parts = fullName.split(" ");
  if (parts.length === 1) return parts[0][0];
  return parts[0][0] + parts[parts.length - 1][0];
}
