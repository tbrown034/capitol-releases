import { NextRequest, NextResponse } from "next/server";
import { sql } from "../../../lib/db";

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function POST(req: NextRequest) {
  let body: { email?: unknown; source?: unknown };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "invalid json" }, { status: 400 });
  }

  const email =
    typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
  const source = typeof body.source === "string" ? body.source.slice(0, 64) : null;

  if (!email || !EMAIL_RE.test(email) || email.length > 254) {
    return NextResponse.json({ error: "invalid email" }, { status: 400 });
  }

  // Resubscribe path: an existing row gets reactivated; the original
  // unsubscribe_token is preserved so the user's old links keep working.
  const rows = (await sql`
    INSERT INTO newsletter_subscribers (email, source)
    VALUES (${email}, ${source})
    ON CONFLICT (email) DO UPDATE
      SET status = 'active',
          unsubscribed_at = NULL,
          source = COALESCE(newsletter_subscribers.source, EXCLUDED.source)
    RETURNING status, subscribed_at = NOW() AS is_new
  `) as { status: string; is_new: boolean }[];

  const result = rows[0];
  return NextResponse.json({
    ok: true,
    status: result?.status ?? "active",
    new: result?.is_new ?? false,
  });
}
