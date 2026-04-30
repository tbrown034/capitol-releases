import { neon, NeonQueryFunction } from "@neondatabase/serverless";

// Neon's serverless driver wraps each query in a `fetch` against the HTTP
// SQL endpoint. On a cold pool or a transient network blip we get a
// "TypeError: fetch failed" that — without a retry — bubbles up as a 500
// and renders the dev error overlay or a runtime crash to users.
//
// Wrap the client in a Proxy so both call shapes are protected:
//   sql`SELECT ... ${id}`     (template-tag)
//   sql.query(text, params)   (parameterized)
//
// We retry once with a brief jittered backoff. A second failure still
// surfaces — at that point it's a real outage, not a cold-start.
const RETRYABLE = /fetch failed|ECONNRESET|ETIMEDOUT|ENOTFOUND|EAI_AGAIN|socket hang up/i;

async function withRetry<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    const cause = err instanceof Error && err.cause ? String((err as { cause: unknown }).cause) : "";
    if (!RETRYABLE.test(msg) && !RETRYABLE.test(cause)) throw err;
    await new Promise((r) => setTimeout(r, 120 + Math.random() * 180));
    return await fn();
  }
}

const rawSql = neon(process.env.DATABASE_URL!);

type AnyFn = (...args: unknown[]) => Promise<unknown>;

export const sql: NeonQueryFunction<false, false> = new Proxy(rawSql, {
  apply(target, thisArg, args) {
    return withRetry(() => (target as unknown as AnyFn).apply(thisArg, args));
  },
  get(target, prop, receiver) {
    const value = Reflect.get(target, prop, receiver);
    if (prop === "query" && typeof value === "function") {
      return (...args: unknown[]) =>
        withRetry(() => (value as AnyFn).apply(target, args));
    }
    return value;
  },
}) as NeonQueryFunction<false, false>;

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
