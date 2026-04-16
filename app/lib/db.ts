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
};

export type PressRelease = {
  id: string;
  senator_id: string;
  title: string;
  published_at: string | null;
  body_text: string | null;
  source_url: string;
  scraped_at: string;
};

export type FeedItem = PressRelease & {
  senator_name: string;
  party: "D" | "R" | "I";
  state: string;
};

export type SenatorWithCount = Senator & {
  release_count: number;
  latest_release: string | null;
};
