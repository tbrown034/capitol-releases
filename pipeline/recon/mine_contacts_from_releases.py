"""
Mine press release body text for press contact names.

Most Senate press releases end with a footer like:
  "Contact: Jane Smith, Press Secretary, (202) 555-1234"
  "Press Contact: John Doe at john_doe@senator.senate.gov"
  "For more information, contact Jane Smith (202) 555-1234"

This script queries the press_releases table and extracts contact info
from body_text, then updates the press directory JSON.

Requires DATABASE_URL environment variable.

Usage:
    python -m pipeline.recon.mine_contacts_from_releases
"""

import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

DIRECTORY = Path(__file__).parent / "senate_press_directory.json"

# Patterns for contact footers in press releases
CONTACT_PATTERNS = [
    # "Contact: First Last" or "Press Contact: First Last"
    re.compile(
        r"(?:press\s+)?contact\s*:\s*"
        r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
        r"(?:\s*[,\-]\s*(.+?))?(?:\n|$)",
        re.IGNORECASE,
    ),
    # "For more information, contact First Last"
    re.compile(
        r"for\s+(?:more\s+)?information\s*,?\s*contact\s+"
        r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        re.IGNORECASE,
    ),
    # "Media contact: First Last"
    re.compile(
        r"media\s+contact\s*:\s*"
        r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        re.IGNORECASE,
    ),
    # "Spokesperson First Last"
    re.compile(
        r"spokesperson\s*:\s*"
        r"([A-Z][a-z]+(?:\s+[A-Z]\.?\s*)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        re.IGNORECASE,
    ),
]

EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
PHONE_PATTERN = re.compile(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")

# Words that are not names
SKIP_NAMES = {
    "press release", "press secretary", "united states", "capitol hill",
    "read more", "click here", "senate office", "washington dc",
    "more information", "press office",
}


def extract_contact_from_text(text: str) -> list[dict]:
    """Extract contact info from a press release body."""
    contacts = []
    # Only look at the last 500 chars (footer area)
    footer = text[-500:] if len(text) > 500 else text

    for pattern in CONTACT_PATTERNS:
        for match in pattern.finditer(footer):
            name = match.group(1).strip()
            if name.lower() in SKIP_NAMES or len(name) < 4:
                continue

            contact = {"name": name}

            # Check for title in group 2 if it exists
            if match.lastindex and match.lastindex >= 2 and match.group(2):
                title = match.group(2).strip()
                # Clean up title (take first part before phone/email)
                title = re.split(r"[\(\d]", title)[0].strip().rstrip(",.- ")
                if title and len(title) < 60:
                    contact["title"] = title

            # Look for email/phone nearby
            context = footer[max(0, match.start() - 50):min(len(footer), match.end() + 200)]
            emails = EMAIL_PATTERN.findall(context)
            phones = PHONE_PATTERN.findall(context)
            if emails:
                contact["email"] = emails[0]
            if phones:
                contact["phone"] = phones[0]

            contacts.append(contact)

    return contacts


def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        print("ERROR: DATABASE_URL not set.")
        print("Set it and re-run, or run this script where the .env.local is sourced.")
        print()
        print("Example:")
        print("  DATABASE_URL='postgres://...' python -m pipeline.recon.mine_contacts_from_releases")
        sys.exit(1)

    try:
        import psycopg2
    except ImportError:
        print("ERROR: psycopg2 not installed. Run: pip install psycopg2-binary")
        sys.exit(1)

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    # Get all press releases with body text, grouped by senator
    cur.execute("""
        SELECT senator_id, body_text
        FROM press_releases
        WHERE body_text IS NOT NULL
          AND length(body_text) > 100
        ORDER BY senator_id, published_at DESC
    """)

    senator_contacts = defaultdict(list)
    total_releases = 0
    total_contacts_found = 0

    for senator_id, body_text in cur:
        total_releases += 1
        contacts = extract_contact_from_text(body_text)
        for c in contacts:
            senator_contacts[senator_id].append(c)
            total_contacts_found += 1

    cur.close()
    conn.close()

    print(f"Processed {total_releases} press releases")
    print(f"Found {total_contacts_found} contact mentions across {len(senator_contacts)} senators")

    # Deduplicate and rank by frequency
    senator_primary = {}
    for senator_id, contacts in senator_contacts.items():
        # Count name frequency
        name_counts = defaultdict(int)
        name_details = {}
        for c in contacts:
            name = c["name"]
            name_counts[name] += 1
            # Keep the most detailed version
            if name not in name_details or len(c) > len(name_details[name]):
                name_details[name] = c

        # Sort by frequency (most common = current press contact)
        ranked = sorted(name_counts.items(), key=lambda x: -x[1])
        senator_primary[senator_id] = {
            "primary": name_details[ranked[0][0]] if ranked else None,
            "primary_mentions": ranked[0][1] if ranked else 0,
            "all_contacts": [
                {**name_details[name], "mentions": count}
                for name, count in ranked[:5]
            ],
        }

    # Update directory if it exists
    if DIRECTORY.exists():
        with open(DIRECTORY) as f:
            directory = json.load(f)

        for senator in directory["senators"]:
            sid = senator["senator_id"]
            if sid in senator_primary:
                info = senator_primary[sid]
                senator["press_contacts_from_releases"] = info["all_contacts"]
                if info["primary"]:
                    senator["primary_press_contact"] = info["primary"]
                    senator["has_named_contact"] = True
                    senator["needs_manual_enrichment"] = False

        # Update summary
        named = sum(1 for s in directory["senators"] if s.get("has_named_contact"))
        directory["summary"]["named_press_contacts"] = named
        directory["summary"]["needs_manual_enrichment"] = len(directory["senators"]) - named
        directory["summary"]["contacts_mined_from_releases"] = len(senator_primary)

        with open(DIRECTORY, "w") as f:
            json.dump(directory, f, indent=2)
        print(f"\nUpdated {DIRECTORY}")
    else:
        # Write standalone output
        output_path = Path(__file__).parent / "mined_press_contacts.json"
        with open(output_path, "w") as f:
            json.dump(senator_primary, f, indent=2)
        print(f"\nWritten to {output_path}")

    # Print summary
    print(f"\n=== CONTACTS MINED FROM RELEASES ===")
    for sid in sorted(senator_primary):
        info = senator_primary[sid]
        if info["primary"]:
            p = info["primary"]
            print(f"  {sid}: {p['name']}"
                  f" ({p.get('title', 'unknown title')})"
                  f" [{info['primary_mentions']} mentions]")


if __name__ == "__main__":
    main()
