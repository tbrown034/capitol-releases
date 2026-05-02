"""Download 437 House headshot photos from bioguide.congress.gov.

Reads pipeline/recon/house_bioguide_ids.json (output of the
2026-05-02 sub-agent A run) and pulls each member's photo from
the Library-of-Congress photo archive at
https://bioguide.congress.gov/bioguide/photo/{first_letter}/{bioguide_id}.jpg

Files land in public/house/{bioguide_id}.jpg, mirroring the
public/senators/{bioguide_id}.jpg pattern Senate already uses
so the /senators/[id] and /house/[id] pages can use the same
src construction.

Idempotent: skips files already on disk above 1 KB.
"""

import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAPPING_FILE = ROOT / "pipeline" / "recon" / "house_bioguide_ids.json"
OUT_DIR = ROOT / "public" / "house"

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
)
THROTTLE_SECONDS = 0.15
MIN_FILE_SIZE = 500  # bytes — bioguide returns small placeholders for missing


def main():
    mapping = json.loads(MAPPING_FILE.read_text())["mapping"]
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    bioguides = sorted(set(mapping.values()))
    total = len(bioguides)
    print(f"Downloading {total} House headshots into {OUT_DIR}/")

    ok = 0
    cached = 0
    missing = 0
    errors = []

    for i, bid in enumerate(bioguides, 1):
        out = OUT_DIR / f"{bid}.jpg"
        if out.exists() and out.stat().st_size >= MIN_FILE_SIZE:
            cached += 1
            ok += 1
            continue

        url = f"https://bioguide.congress.gov/bioguide/photo/{bid[0]}/{bid}.jpg"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
                if len(data) < MIN_FILE_SIZE:
                    missing += 1
                    continue
                out.write_bytes(data)
                ok += 1
        except urllib.error.HTTPError as e:
            if e.code == 404:
                missing += 1
            else:
                errors.append((bid, e.code))
        except Exception as e:
            errors.append((bid, type(e).__name__))

        if i % 50 == 0:
            files_glob = "*.jpg"
            print(
                f"  {i}/{total}  ok={ok} cached={cached} "
                f"missing={missing} errs={len(errors)} "
                f"on disk={len(list(OUT_DIR.glob(files_glob)))}"
            )
        time.sleep(THROTTLE_SECONDS)

    print()
    print(f"FINAL: ok={ok} cached={cached} missing(404)={missing} errors={len(errors)}")
    if errors:
        print(f"Sample errors: {errors[:10]}")
    files_glob = "*.jpg"
    final = list(OUT_DIR.glob(files_glob))
    print(f"Files on disk: {len(final)}")


if __name__ == "__main__":
    main()
