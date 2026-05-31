import { NextRequest, NextResponse } from "next/server";
import { sql } from "../../../lib/db";

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderPage(body: string, status = 200) {
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Unsubscribe · Capitol Releases</title>
<style>
  body { font-family: ui-serif, Georgia, serif; max-width: 32rem; margin: 4rem auto; padding: 0 1.25rem; color: #171717; }
  h1 { font-size: 1.5rem; margin-bottom: 1rem; }
  p { line-height: 1.6; color: #525252; font-size: 0.95rem; }
  button { background: #171717; border: 0; color: white; cursor: pointer; font: inherit; padding: 0.65rem 0.9rem; }
  a { color: #171717; }
</style>
</head>
<body>
${body}
</body>
</html>`;
  return new NextResponse(html, {
    status,
    headers: { "content-type": "text/html; charset=utf-8" },
  });
}

async function unsubscribe(token: string) {
  if (!UUID_RE.test(token)) {
    return renderPage("<h1>Invalid unsubscribe link.</h1>", 400);
  }

  const rows = (await sql`
    UPDATE newsletter_subscribers
    SET status = 'unsubscribed',
        unsubscribed_at = NOW()
    WHERE unsubscribe_token = ${token}::uuid
    RETURNING email
  `) as { email: string }[];

  if (rows.length === 0) {
    return renderPage("<h1>This link is no longer valid.</h1>", 404);
  }

  return renderPage(`
  <h1>You're unsubscribed.</h1>
  <p>${escapeHtml(rows[0].email)} will no longer receive the Capitol Releases daily brief.</p>
  <p>If this was a mistake, you can <a href="/brief">resubscribe at any time</a>.</p>
`);
}

export async function POST(req: NextRequest) {
  let token = req.nextUrl.searchParams.get("token") ?? "";
  if (!token) {
    try {
      const formData = await req.formData();
      token = String(formData.get("token") ?? "");
    } catch {
      token = "";
    }
  }
  return unsubscribe(token);
}
