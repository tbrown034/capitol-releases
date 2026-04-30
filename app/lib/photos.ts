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

// Also build senator_id -> bioguide_id map
// senator_id format: "warren-elizabeth", name format: "Elizabeth Warren"
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

export function getSenatorPhotoUrl(fullName: string, senatorId?: string): string | null {
  // Non-senate members (e.g. White House) use senator_id as the filename directly.
  if (senatorId === "whitehouse") return `/senators/whitehouse.jpg`;

  // Texas state senators have IDs like "tx-d29-blanco" and photos stored
  // at /state-senators/tx/dXX.jpg. Pull the district number out of the ID
  // and resolve directly — no bioguide lookup applies.
  if (senatorId?.startsWith("tx-d")) {
    const m = senatorId.match(/^tx-d(\d{2})-/);
    if (m) return `/state-senators/tx/d${m[1]}.jpg`;
  }

  // Try senator_id first (most reliable)
  if (senatorId) {
    const byId = idToBioguide.get(senatorId);
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
export function getSenatorHref(senatorId: string): string {
  if (senatorId.startsWith("tx-")) return `/texas/${senatorId}`;
  return `/senators/${senatorId}`;
}

export function getInitials(fullName: string): string {
  const parts = fullName.split(" ");
  if (parts.length === 1) return parts[0][0];
  return parts[0][0] + parts[parts.length - 1][0];
}
