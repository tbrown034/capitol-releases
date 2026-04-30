"""
Email signup recon for all 100 senators.

Checks each senator's website for newsletter/email signup pages
and identifies the platform (GovDelivery, Mailchimp, custom form, etc).

Output: pipeline/recon/email_signup_results.json
"""

import asyncio
import json
import re
import time
from pathlib import Path

import httpx

SEEDS = Path(__file__).parent.parent / "seeds" / "senate.json"
OUTPUT = Path(__file__).parent / "email_signup_results.json"

# Common signup URL paths on senate.gov sites
SIGNUP_PATHS = [
    "/subscribe",
    "/newsletter",
    "/signup",
    "/contact/newsletter",
    "/contact/subscribe",
    "/email-signup",
    "/contact/email-signup",
    "/newsroom/newsletter",
    "/connect/newsletter",
    "/connect/subscribe",
]

# Patterns that indicate email signup functionality in page HTML
SIGNUP_INDICATORS = [
    r'govdelivery\.com',
    r'public\.govdelivery\.com/accounts/(US\w+)',
    r'mailchimp\.com',
    r'list-manage\.com',
    r'constantcontact\.com',
    r'newsletter[_-]?signup',
    r'email[_-]?signup',
    r'subscribe.*newsletter',
    r'sign\s*up.*updates',
    r'action=["\'].*subscribe',
    r'name=["\']EMAIL["\']',
    r'type=["\']email["\'].*subscribe',
]

GOVDELIVERY_PATTERN = re.compile(
    r'(?:public\.)?govdelivery\.com/accounts/(\w+)', re.IGNORECASE
)
MAILCHIMP_PATTERN = re.compile(
    r'(?:list-manage\.com|mailchimp\.com)', re.IGNORECASE
)
CONSTANT_CONTACT_PATTERN = re.compile(
    r'constantcontact\.com', re.IGNORECASE
)


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}


async def check_url(client: httpx.AsyncClient, url: str) -> dict | None:
    """Check if a URL exists and return response info."""
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15)
        if resp.status_code == 200:
            return {
                "url": str(resp.url),  # final URL after redirects
                "status": resp.status_code,
                "html_length": len(resp.text),
                "text": resp.text,
            }
        return None
    except Exception:
        return None


def detect_platform(html: str) -> dict:
    """Detect email platform from page HTML."""
    result = {"platform": "unknown", "details": {}}

    gd_match = GOVDELIVERY_PATTERN.search(html)
    if gd_match:
        result["platform"] = "govdelivery"
        result["details"]["account_code"] = gd_match.group(1)
        # Try to extract the full signup URL
        gd_url_match = re.search(
            r'(https?://public\.govdelivery\.com/accounts/\w+/subscriber/\w+[^"\'<>\s]*)',
            html
        )
        if gd_url_match:
            result["details"]["signup_url"] = gd_url_match.group(1)
        return result

    if MAILCHIMP_PATTERN.search(html):
        result["platform"] = "mailchimp"
        mc_match = re.search(
            r'(https?://[^"\'<>\s]*(?:list-manage|mailchimp)\.com[^"\'<>\s]*)',
            html
        )
        if mc_match:
            result["details"]["signup_url"] = mc_match.group(1)
        return result

    if CONSTANT_CONTACT_PATTERN.search(html):
        result["platform"] = "constant_contact"
        return result

    # Check for generic email signup forms
    has_email_input = bool(re.search(r'type=["\']email["\']', html, re.I))
    has_subscribe = bool(re.search(r'subscribe|sign.?up|newsletter', html, re.I))
    if has_email_input and has_subscribe:
        result["platform"] = "custom_form"

    return result


async def recon_senator(
    client: httpx.AsyncClient,
    senator: dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    """Run email signup recon for one senator."""
    async with semaphore:
        base_url = senator["official_url"].rstrip("/")
        senator_id = senator["senator_id"]
        result = {
            "senator_id": senator_id,
            "full_name": senator["full_name"],
            "state": senator["state"],
            "party": senator["party"],
            "official_url": base_url,
            "signup_pages_found": [],
            "platform": "unknown",
            "platform_details": {},
            "govdelivery_account": None,
            "recommended_signup_url": None,
            "homepage_has_signup": False,
            "notes": "",
            "recon_timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        }

        # 1. Check homepage for signup indicators
        homepage = await check_url(client, base_url)
        if homepage:
            platform_info = detect_platform(homepage["text"])
            if platform_info["platform"] != "unknown":
                result["homepage_has_signup"] = True
                result["platform"] = platform_info["platform"]
                result["platform_details"] = platform_info["details"]
                if platform_info["platform"] == "govdelivery":
                    result["govdelivery_account"] = platform_info["details"].get(
                        "account_code"
                    )

        # 2. Check common signup paths
        for path in SIGNUP_PATHS:
            url = f"{base_url}{path}"
            resp = await check_url(client, url)
            if resp:
                page_platform = detect_platform(resp["text"])
                entry = {
                    "path": path,
                    "final_url": resp["url"],
                    "platform": page_platform["platform"],
                }
                result["signup_pages_found"].append(entry)

                # Update senator-level platform if we found something specific
                if page_platform["platform"] != "unknown":
                    result["platform"] = page_platform["platform"]
                    result["platform_details"] = page_platform["details"]
                    if page_platform["platform"] == "govdelivery":
                        result["govdelivery_account"] = page_platform[
                            "details"
                        ].get("account_code")

        # 3. Check for direct GovDelivery page (common pattern)
        # Many senators use: public.govdelivery.com/accounts/USSENATORLASTNAME
        last_name = senator_id.split("-")[0].upper()
        for prefix in [f"USSEN{last_name}", f"USSENATE{last_name}"]:
            gd_url = f"https://public.govdelivery.com/accounts/{prefix}/subscriber/new"
            resp = await check_url(client, gd_url)
            if resp and "govdelivery" in resp["url"].lower():
                result["platform"] = "govdelivery"
                result["govdelivery_account"] = prefix
                result["platform_details"]["signup_url"] = resp["url"]
                result["signup_pages_found"].append({
                    "path": f"govdelivery_direct/{prefix}",
                    "final_url": resp["url"],
                    "platform": "govdelivery",
                })
                break

        # Set recommended signup URL
        if result["platform_details"].get("signup_url"):
            result["recommended_signup_url"] = result["platform_details"]["signup_url"]
        elif result["signup_pages_found"]:
            result["recommended_signup_url"] = result["signup_pages_found"][0][
                "final_url"
            ]

        # Generate notes
        if not result["signup_pages_found"] and not result["homepage_has_signup"]:
            result["notes"] = "No email signup found via automated recon. Manual check needed."
        elif result["platform"] == "govdelivery":
            result["notes"] = f"GovDelivery account: {result['govdelivery_account']}"
        elif result["platform"] == "mailchimp":
            result["notes"] = "Mailchimp-based signup"
        elif result["platform"] == "custom_form":
            result["notes"] = "Custom signup form on site"

        print(f"  {senator_id}: {result['platform']} ({len(result['signup_pages_found'])} pages)")
        return result


async def main():
    with open(SEEDS) as f:
        senators = json.load(f)["members"]

    print(f"Running email signup recon for {len(senators)} senators...")
    print()

    semaphore = asyncio.Semaphore(10)  # limit concurrency

    async with httpx.AsyncClient(headers=HEADERS) as client:
        tasks = [recon_senator(client, s, semaphore) for s in senators]
        results = await asyncio.gather(*tasks)

    # Sort by senator_id
    results.sort(key=lambda r: r["senator_id"])

    # Summary
    platforms = {}
    for r in results:
        p = r["platform"]
        platforms[p] = platforms.get(p, 0) + 1

    print()
    print("=== SUMMARY ===")
    for platform, count in sorted(platforms.items(), key=lambda x: -x[1]):
        print(f"  {platform}: {count}")
    print(f"  Total: {len(results)}")

    found = sum(1 for r in results if r["platform"] != "unknown")
    print(f"\n  Signup found: {found}/{len(results)}")
    print(f"  Manual check needed: {len(results) - found}")

    # Write output
    output = {
        "recon_type": "email_signup",
        "run_date": time.strftime("%Y-%m-%d"),
        "total_senators": len(results),
        "summary": {
            "by_platform": platforms,
            "signup_found": found,
            "manual_check_needed": len(results) - found,
        },
        "senators": results,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(output, f, indent=2)

    print(f"\nResults written to {OUTPUT}")


if __name__ == "__main__":
    asyncio.run(main())
