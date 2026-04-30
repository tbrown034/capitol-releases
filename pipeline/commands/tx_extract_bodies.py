"""Extract body text from each TX press-release PDF and store in body_text.

The TX collector archives the listing entry but defers the body to the
linked PDF. This command closes that gap by downloading the PDF and
running pypdf text extraction. We also compute content_hash so future
re-extractions can detect post-publication edits.

Usage:
    python -m pipeline tx-extract                  # process all unfilled
    python -m pipeline tx-extract --senator <id>   # one senator
    python -m pipeline tx-extract --limit 10       # cap for testing
    python -m pipeline tx-extract --dry-run        # show what would change

PDFs are typed-text (not scanned), so pypdf gets clean text. We normalize
two common artifacts: word-breaks across visual lines (Stoc\\nkton) and
runs of small-font header whitespace.
"""
import argparse
import hashlib
import io
import os
import re
import sys
import time
from pathlib import Path

import httpx
import psycopg2
from bs4 import BeautifulSoup

try:
    import pdfplumber  # type: ignore
except ImportError:
    print("Missing dependency: pip install pdfplumber", file=sys.stderr)
    sys.exit(2)


def _load_env():
    if "DATABASE_URL" in os.environ:
        return
    for p in [Path(".env"), Path("pipeline/.env")]:
        if p.exists():
            for line in p.read_text().splitlines():
                if line.strip() and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_MULTI_WS = re.compile(r"[ \t]{2,}")
_MULTI_NL = re.compile(r"\n{3,}")


def _rejoin_word_per_line(s: str) -> str:
    """Some TX PDFs lay every word in its own text box, so pypdf emits a
    line per word with blank lines between. Detect runs of short single-
    word lines (ignoring blanks within the run) and re-join them with
    spaces. Defines a "fragment line" as <=3 words and <=24 chars. Three
    or more in a near-contiguous run = per-word PDF; we collapse the run.
    """
    lines = s.split("\n")
    out: list[str] = []
    buf: list[str] = []

    def is_fragment(line: str) -> bool:
        line = line.strip()
        if not line:
            return False
        if len(line) > 24:
            return False
        return len(line.split()) <= 3

    def flush():
        if len(buf) >= 3:
            out.append(" ".join(buf))
        else:
            out.extend(buf)
        buf.clear()

    for line in lines:
        stripped = line.strip()
        if is_fragment(stripped):
            buf.append(stripped)
        elif not stripped and buf:
            # Blank line inside a fragment run — keep buffering. The
            # blank is consumed; we don't preserve it within a per-word
            # PDF region because the original document's layout is the
            # noise we're cleaning up.
            continue
        else:
            flush()
            out.append(line)
    flush()
    return "\n".join(out)


def clean_pdf_text(raw: str) -> str:
    """Light cleanup of pdfplumber output.

    Earlier versions had aggressive word-rejoin regexes — designed for
    pypdf's mid-word breaks (Stoc\\nkton) — which smashed valid
    line-wrapped pairs in pdfplumber output (member\\ncommittee →
    membercommittee). Removed; pdfplumber preserves word boundaries
    correctly so we only strip cosmetic whitespace.
    """
    if not raw:
        return ""
    # Strip header whitespace runs
    s = _MULTI_WS.sub(" ", raw)
    # Collapse big newline gaps to two
    s = _MULTI_NL.sub("\n\n", s)
    # Strip leading/trailing whitespace per line
    s = "\n".join(line.strip() for line in s.split("\n"))
    # Re-join word-per-line PDFs (every word in its own text box). Run
    # after per-line strip so the fragment detector sees actual content.
    s = _rejoin_word_per_line(s)
    # Then collapse blank-line runs again post-strip
    s = _MULTI_NL.sub("\n\n", s)
    # Strip ### / -30- end-of-release markers (PDF templates often append
    # these to signal end-of-document; they don't add meaning).
    s = _TRAILING_MARKERS.sub("", s)
    return s.strip()


def extract_pdf_text(content: bytes) -> str:
    """Extract text from a PDF byte stream using pdfplumber.

    pdfplumber handles inter-word spacing in PDFs where words are visually
    separated by x-coordinate position rather than space characters — a
    common case in TX press releases that pypdf concatenates as
    "membercommitteeappointmentsforthe". x_tolerance=3 specifically fixes
    headline-to-body boundaries ("ASSIGNMENTSAUSTIN" splits to
    "ASSIGNMENTS\\nAUSTIN") that x_tolerance=2 missed.
    """
    pages: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            t = page.extract_text(x_tolerance=3, y_tolerance=3) or ""
            pages.append(t)
    return "\n\n".join(pages)


# Common PDF end-of-document markers TX templates leave behind.
_TRAILING_MARKERS = re.compile(r"\n+#{2,}\s*$|\n+-\s*30\s*-\s*$", re.MULTILINE)


# Boilerplate that appears at the top of every senate.texas.gov press.php
# page before the actual release content. Strip it so the body starts at
# the headline.
_PRESS_PHP_NAV = re.compile(
    r"^.*?(?:« Return to the home page for Senator [^\n]+|printer-friendly)\s*",
    re.DOTALL | re.IGNORECASE,
)


def extract_html_text(content: bytes, url: str) -> str:
    """Extract body text from a senate.texas.gov press.php HTML page.

    The page wraps the release in <main>; we get all text inside, then
    strip the predictable navigation boilerplate at the top.
    """
    soup = BeautifulSoup(content, "lxml")
    container = soup.select_one("main") or soup.body
    if not container:
        return ""
    # Drop nav-only nodes
    for sel in ["nav", "header", "footer", "script", "style", ".breadcrumb"]:
        for n in container.select(sel):
            n.decompose()
    text = container.get_text(" ", strip=False)
    # Strip the "« Return to the home page for Senator X printer-friendly"
    # preamble; what follows is the actual release.
    text = _PRESS_PHP_NAV.sub("", text)
    return text


def main():
    _load_env()
    parser = argparse.ArgumentParser()
    parser.add_argument("--senator", help="senator_id to limit to")
    parser.add_argument("--limit", type=int, help="cap on records to process")
    parser.add_argument("--dry-run", action="store_true", help="don't write DB")
    parser.add_argument("--reextract", action="store_true",
                        help="redo records that already have body_text")
    args = parser.parse_args()

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    where = [
        "s.chamber = 'tx_senate'",
        "pr.deleted_at IS NULL",
        "pr.content_type = 'press_release'",
        # Both PDF and HTML press.php URLs are in scope; videoplayer.php is
        # explicitly excluded (videos have no body to extract).
        "(lower(pr.source_url) LIKE '%.pdf' OR pr.source_url LIKE '%press.php%')",
    ]
    if not args.reextract:
        where.append("(pr.body_text IS NULL OR length(pr.body_text) < 50)")
    if args.senator:
        where.append(f"pr.senator_id = '{args.senator}'")

    sql = f"""
        SELECT pr.id, pr.senator_id, pr.title, pr.source_url
        FROM press_releases pr
        JOIN senators s ON s.id = pr.senator_id
        WHERE {" AND ".join(where)}
        ORDER BY pr.published_at DESC NULLS LAST
    """
    if args.limit:
        sql += f" LIMIT {args.limit}"
    cur.execute(sql)
    rows = cur.fetchall()
    print(f"Found {len(rows)} TX PDF records to process")

    ua = "Mozilla/5.0 (compatible; CapitolReleases/1.0 body-extractor)"
    client = httpx.Client(timeout=30.0, headers={"User-Agent": ua}, follow_redirects=True)

    ok = 0
    failed = []
    for i, (rid, sid, title, source_url) in enumerate(rows, 1):
        try:
            time.sleep(0.6)  # polite
            r = client.get(source_url)
            if r.status_code != 200:
                failed.append((rid, source_url, f"HTTP {r.status_code}"))
                print(f"  [{i}/{len(rows)}] {sid:25} HTTP {r.status_code}  {title[:50]}")
                continue
            ct = r.headers.get("content-type", "")
            url_lower = source_url.lower()
            if url_lower.endswith(".pdf") or "pdf" in ct.lower():
                raw = extract_pdf_text(r.content)
            elif "press.php" in url_lower or "html" in ct.lower():
                raw = extract_html_text(r.content, source_url)
            else:
                failed.append((rid, source_url, f"Unknown content-type: {ct}"))
                print(f"  [{i}/{len(rows)}] {sid:25} unknown  {title[:50]}")
                continue
            cleaned = clean_pdf_text(raw)
            if not cleaned or len(cleaned) < 50:
                failed.append((rid, source_url, f"Empty/tiny extract ({len(cleaned)} chars)"))
                print(f"  [{i}/{len(rows)}] {sid:25} short-text ({len(cleaned)})  {title[:50]}")
                continue

            content_hash = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()

            if args.dry_run:
                print(f"  [{i}/{len(rows)}] DRY  {sid:25} {len(cleaned):>5} chars  {title[:50]}")
            else:
                cur.execute(
                    """UPDATE press_releases
                       SET body_text = %s, content_hash = %s, updated_at = NOW()
                       WHERE id = %s""",
                    (cleaned, content_hash, rid),
                )
                conn.commit()
                print(f"  [{i}/{len(rows)}] OK   {sid:25} {len(cleaned):>5} chars  {title[:50]}")
            ok += 1
        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            failed.append((rid, source_url, f"{type(e).__name__}: {e}"))
            print(f"  [{i}/{len(rows)}] ERR  {sid:25} {type(e).__name__}: {str(e)[:50]}")

    print()
    print(f"Summary: {ok}/{len(rows)} extracted")
    if failed:
        print(f"Failures: {len(failed)}")
        for rid, url, err in failed[:10]:
            print(f"  {rid} {url}: {err}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
