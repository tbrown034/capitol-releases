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
