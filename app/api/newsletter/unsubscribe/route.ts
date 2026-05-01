import { NextRequest, NextResponse } from "next/server";
import { sql } from "../../../lib/db";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function GET(req: NextRequest) {
  const token = req.nextUrl.searchParams.get("token") ?? "";
  if (!UUID_RE.test(token)) {
    return new NextResponse("Invalid unsubscribe link.", { status: 400 });
  }

  const rows = (await sql`
    UPDATE newsletter_subscribers
    SET status = 'unsubscribed',
        unsubscribed_at = NOW()
    WHERE unsubscribe_token = ${token}::uuid
    RETURNING email
  `) as { email: string }[];

  if (rows.length === 0) {
    return new NextResponse("This link is no longer valid.", { status: 404 });
  }

  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Unsubscribed — Capitol Releases</title>
<style>
  body { font-family: ui-serif, Georgia, serif; max-width: 32rem; margin: 4rem auto; padding: 0 1.25rem; color: #171717; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; }
  p { line-height: 1.6; color: #525252; font-size: 0.95rem; }
  a { color: #171717; }
</style>
</head>
<body>
  <h1>You're unsubscribed.</h1>
  <p>${rows[0].email} will no longer receive the Capitol Releases daily brief.</p>
  <p>If this was a mistake, you can <a href="/brief">resubscribe at any time</a>.</p>
</body>
</html>`;
  return new NextResponse(html, {
    status: 200,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}
