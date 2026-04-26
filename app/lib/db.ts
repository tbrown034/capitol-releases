import { neon, NeonQueryFunction } from "@neondatabase/serverless";

export const sql: NeonQueryFunction<false, false> = neon(
  process.env.DATABASE_URL!
);

export type Senator = {
  id: string;
  full_name: string;
  party: "D" | "R" | "I";
  state: string;
  official_url: string;
  press_release_url: string | null;
  parser_family: string | null;
  confidence: number | null;
  senate_class: number | null;
  first_term_start: string | null;
  current_term_end: string | null;
  chamber: string;
};

export type ContentType =
  | "press_release"
  | "statement"
  | "op_ed"
  | "blog"
  | "letter"
  | "photo_release"
  | "floor_statement"
  | "presidential_action"
  | "other";

export type PressRelease = {
  id: string;
  senator_id: string;
  title: string;
  published_at: string | null;
  body_text: string | null;
  source_url: string;
  scraped_at: string;
  content_type: ContentType;
};

export type FeedItem = PressRelease & {
  senator_name: string;
  party: "D" | "R" | "I";
  state: string;
};

export type TypeBreakdown = Partial<Record<ContentType, number>>;

export type SenatorWithCount = Senator & {
  release_count: number;
  latest_release: string | null;
  earliest_release: string | null;
  type_breakdown: TypeBreakdown;
};
