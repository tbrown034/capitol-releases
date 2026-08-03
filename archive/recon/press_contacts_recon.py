"""
Press contacts recon for all 100 senators.

Scrapes senator websites for press secretaries, communications directors,
spokespeople, and media liaison contact info.

Common locations:
- /about (staff listings)
- /contact (press office info)
- /about/staff or /about/biography
- /newsroom (sometimes lists press contact)
- Press release footers (often contain "Contact: Name, email")

Output: pipeline/recon/press_contacts_results.json
"""

import asyncio
import json
import re
import time
from pathlib import Path

import httpx

SEEDS = Path(__file__).parent.parent / "seeds" / "senate.json"
OUTPUT = Path(__file__).parent / "press_contacts_results.json"

# Pages likely to contain press staff info
CONTACT_PATHS = [
    "",  # homepage
    "/about",
    "/about/staff",
    "/about/biography",
    "/about/the-senator",
    "/contact",
    "/contact/press",
    "/contact/media",
    "/newsroom",
    "/news",
    "/press",
    "/media",
    "/about/offices",
]

# Titles that indicate press/comms staff
PRESS_TITLES = [
    r"press\s+secretary",
    r"deputy\s+press\s+secretary",
    r"communications?\s+director",
    r"deputy\s+communications?\s+director",
    r"spokesperson",
    r"media\s+(?:liaison|relations|contact|director|coordinator)",
    r"director\s+of\s+communications?",
    r"chief\s+of\s+communications?",
    r"press\s+(?:aide|assistant|contact|office|rep)",
    r"digital\s+(?:director|communications?)",
    r"senior\s+communications?\s+(?:advisor|adviser)",
    r"communications?\s+(?:manager|advisor|adviser|strategist|specialist|coordinator)",
    r"public\s+(?:affairs|relations)\s+(?:director|officer|specialist)",
]

PRESS_TITLE_PATTERN = re.compile(
    r"(" + "|".join(PRESS_TITLES) + r")", re.IGNORECASE
)

# Email pattern
EMAIL_PATTERN = re.compile(
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
)

# Phone pattern (US)
PHONE_PATTERN = re.compile(
    r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}"
)

# Pattern for "Contact: Name" or "Press Contact: Name" in press release footers
CONTACT_LINE_PATTERN = re.compile(
    r"(?:press\s+)?contact[s]?\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})",
    re.IGNORECASE,
)

# Pattern for "Name, Title" or "Name - Title" near press titles
NAME_TITLE_PATTERN = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
    r"\s*[,\-\|]\s*"
    r"(" + "|".join(PRESS_TITLES) + r")",
    re.IGNORECASE,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}


def clean_text(html: str) -> str:
    """Strip HTML tags and normalize whitespace."""
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"&#\d+;", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def extract_contacts_from_html(html: str, url: str) -> list[dict]:
    """Extract press contacts from page HTML."""
    contacts = []
    text = clean_text(html)

    # Method 1: "Name, Title" or "Name - Title" pattern
    for match in NAME_TITLE_PATTERN.finditer(text):
        name = match.group(1).strip()
        title = match.group(2).strip()
        # Skip false positives (too short, all caps, etc.)
        if len(name) < 4 or name.isupper():
            continue
        contact = {
            "name": name,
            "title": title.title(),
            "source_url": url,
            "extraction_method": "name_title_pattern",
        }
        # Look for email near the match (within 200 chars)
        context_start = max(0, match.start() - 200)
        context_end = min(len(text), match.end() + 200)
        context = text[context_start:context_end]
        emails = EMAIL_PATTERN.findall(context)
        phones = PHONE_PATTERN.findall(context)
        if emails:
            contact["email"] = emails[0]
        if phones:
            contact["phone"] = phones[0]
        contacts.append(contact)

    # Method 2: "Contact: Name" lines (common in press release footers)
    for match in CONTACT_LINE_PATTERN.finditer(text):
        name = match.group(1).strip()
        if len(name) < 4 or name.isupper():
            continue
        contact = {
            "name": name,
            "title": "Press Contact",
            "source_url": url,
            "extraction_method": "contact_line",
        }
        context_start = max(0, match.start() - 100)
        context_end = min(len(text), match.end() + 300)
        context = text[context_start:context_end]
        emails = EMAIL_PATTERN.findall(context)
        phones = PHONE_PATTERN.findall(context)
        if emails:
            contact["email"] = emails[0]
        if phones:
            contact["phone"] = phones[0]
        contacts.append(contact)

    # Method 3: Look for press-related titles and grab nearby names from HTML structure
    # Search in the raw HTML for structured staff listings
    staff_sections = re.findall(
        r"(?:staff|team|about|contact|press).*?(?:</(?:div|section|ul|table)>)",
        html, re.IGNORECASE | re.DOTALL
    )
    for section in staff_sections:
        section_text = clean_text(section)
        for title_match in PRESS_TITLE_PATTERN.finditer(section_text):
            title = title_match.group(1).strip()
            # Look for a name near this title (before or after, within 100 chars)
            context_start = max(0, title_match.start() - 100)
            context_end = min(len(section_text), title_match.end() + 100)
            context = section_text[context_start:context_end]
            # Find capitalized names
            name_matches = re.findall(
                r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
                context,
            )
            for name in name_matches:
                if len(name) < 4 or name == title.title():
                    continue
                # Skip if it's a common word pair
                skip_words = {
                    "Press Secretary", "Communications Director", "Press Office",
                    "United States", "Capitol Hill", "Senate Office",
                    "Contact Us", "Press Release", "Read More",
                }
                if name in skip_words:
                    continue
                contact = {
                    "name": name,
                    "title": title.title(),
                    "source_url": url,
                    "extraction_method": "staff_section",
                }
                emails = EMAIL_PATTERN.findall(context)
                phones = PHONE_PATTERN.findall(context)
                if emails:
                    contact["email"] = emails[0]
                if phones:
                    contact["phone"] = phones[0]
                contacts.append(contact)

    # Method 4: Look for generic press office email/phone
    press_emails = re.findall(
        r"(press@[a-zA-Z0-9.\-]+\.senate\.gov|"
        r"media@[a-zA-Z0-9.\-]+\.senate\.gov|"
        r"communications@[a-zA-Z0-9.\-]+\.senate\.gov)",
        html, re.IGNORECASE,
    )
    for email in press_emails:
        contacts.append({
            "name": None,
            "title": "Press Office",
            "email": email.lower(),
            "source_url": url,
            "extraction_method": "press_email_pattern",
        })

    return contacts


async def fetch_page(client: httpx.AsyncClient, url: str) -> str | None:
    """Fetch a page, return HTML or None."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15)
        if resp.status_code == 200:
            return resp.text
    except Exception:
        pass
    return None


def dedup_contacts(contacts: list[dict]) -> list[dict]:
    """Remove duplicate contacts, preferring entries with more info."""
    seen = {}
    for c in contacts:
        name = (c.get("name") or "").lower()
        title = (c.get("title") or "").lower()
        key = (name, title)
        if key == ("", ""):
            key = (c.get("email", ""), title)
        existing = seen.get(key)
        if existing is None:
            seen[key] = c
        else:
            # Keep the one with more fields filled
            existing_score = sum(1 for v in existing.values() if v)
            new_score = sum(1 for v in c.values() if v)
            if new_score > existing_score:
                seen[key] = c
    return list(seen.values())


async def recon_senator(
    client: httpx.AsyncClient,
    senator: dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Run press contact recon for one senator."""
    async with semaphore:
        base_url = senator["official_url"].rstrip("/")
        senator_id = senator["senator_id"]

        all_contacts = []
        pages_checked = []

        for path in CONTACT_PATHS:
            url = f"{base_url}{path}"
            html = await fetch_page(client, url)
            if html:
                pages_checked.append(path or "/")
                contacts = extract_contacts_from_html(html, url)
                all_contacts.extend(contacts)

        # Also check recent press releases for "Contact:" footers
        pr_url = senator.get("press_release_url")
        if pr_url:
            html = await fetch_page(client, pr_url)
            if html:
                pages_checked.append("press_releases_listing")
                contacts = extract_contacts_from_html(html, pr_url)
                all_contacts.extend(contacts)

        # Dedup
        all_contacts = dedup_contacts(all_contacts)

        # Categorize
        named_contacts = [c for c in all_contacts if c.get("name")]
        press_emails = [c for c in all_contacts if c.get("extraction_method") == "press_email_pattern"]

        result = {
            "senator_id": senator_id,
            "full_name": senator["full_name"],
            "state": senator["state"],
            "party": senator["party"],
            "official_url": base_url,
            "pages_checked": pages_checked,
            "contacts": all_contacts,
            "named_contacts_count": len(named_contacts),
            "press_office_email": press_emails[0]["email"] if press_emails else None,
            "primary_press_contact": named_contacts[0] if named_contacts else None,
            "status": "found" if named_contacts else ("email_only" if press_emails else "not_found"),
            "recon_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        status_icon = "+" if named_contacts else ("~" if press_emails else "-")
        print(f"  {status_icon} {senator_id}: {len(named_contacts)} named, {len(press_emails)} emails")
        return result


async def main():
    with open(SEEDS) as f:
        senators = json.load(f)["members"]

    print(f"Running press contacts recon for {len(senators)} senators...")
    print(f"Checking {len(CONTACT_PATHS)} paths per senator + press release listings")
    print()

    semaphore = asyncio.Semaphore(8)  # conservative concurrency

    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = [recon_senator(client, s, semaphore) for s in senators]
        results = await asyncio.gather(*tasks)

    results.sort(key=lambda r: r["senator_id"])

    # Summary
    found = sum(1 for r in results if r["status"] == "found")
    email_only = sum(1 for r in results if r["status"] == "email_only")
    not_found = sum(1 for r in results if r["status"] == "not_found")
    total_named = sum(r["named_contacts_count"] for r in results)
    total_emails = sum(1 for r in results if r["press_office_email"])

    print()
    print("=== SUMMARY ===")
    print(f"  Named press contacts found: {found} senators ({total_named} total contacts)")
    print(f"  Press email only: {email_only} senators")
    print(f"  Nothing found: {not_found} senators")
    print(f"  Press office emails: {total_emails}")
    print(f"  Total: {len(results)}")

    output = {
        "recon_type": "press_contacts",
        "run_date": time.strftime("%Y-%m-%d"),
        "description": "Automated recon of senator press offices, spokespeople, communications directors, and media contacts.",
        "methodology": [
            f"HTTP GET to {len(CONTACT_PATHS)} common pages per senator",
            "Regex extraction of Name + Title patterns",
            "Contact: line parsing from press release footers",
            "Press office email detection (press@, media@, communications@)",
            "Staff section parsing from structured HTML",
        ],
        "limitations": [
            "Cannot detect JS-rendered staff pages (would need Playwright)",
            "Name extraction is heuristic -- may miss unconventional formats",
            "Does not check individual press release detail pages (only listings)",
            "Staff turnover means contacts go stale quickly",
        ],
        "summary": {
            "total_senators": len(results),
            "named_contacts_found": found,
            "email_only": email_only,
            "not_found": not_found,
            "total_named_contacts": total_named,
            "total_press_emails": total_emails,
        },
        "senators": results,
    }

    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults written to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
