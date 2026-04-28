// Display metadata for content types. Kept in its own module (no DB import)
// so client components can import these constants without pulling in the
// neon() runtime — which throws on the client because DATABASE_URL is
// server-only.

import type { ContentType } from "./db";

export const CONTENT_TYPE_LABEL: Record<ContentType, string> = {
  press_release: "Press release",
  statement: "Statement",
  op_ed: "Op-ed",
  blog: "Blog / newsletter",
  letter: "Letter",
  photo_release: "Photo release",
  floor_statement: "Floor statement",
  presidential_action: "Presidential action",
  other: "Other",
};

export const CONTENT_TYPE_LABEL_SHORT: Record<ContentType, string> = {
  press_release: "Press",
  statement: "Statement",
  op_ed: "Op-ed",
  blog: "Blog",
  letter: "Letter",
  photo_release: "Photo",
  floor_statement: "Floor",
  presidential_action: "Pres. action",
  other: "Other",
};

export const CONTENT_TYPE_PLURAL: Record<ContentType, string> = {
  press_release: "press releases",
  statement: "statements",
  op_ed: "op-eds",
  blog: "blog posts",
  letter: "letters",
  photo_release: "photo releases",
  floor_statement: "floor statements",
  presidential_action: "presidential actions",
  other: "other",
};

// Display order for filter chips + breakdowns. press_release leads.
// photo_release is intentionally omitted — excluded from every UI surface.
export const CONTENT_TYPE_ORDER: ContentType[] = [
  "press_release",
  "statement",
  "op_ed",
  "blog",
  "letter",
  "floor_statement",
  "presidential_action",
  "other",
];
