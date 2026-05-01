"""QC checks for the state expansion recon artifacts."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "pipeline" / "recon" / "state_expansion_source_inventory_2026_05_01.json"
BROAD_RENDER = ROOT / "pipeline" / "recon" / "state_expansion_render_probe_2026_05_01.json"
SOS_RENDER = ROOT / "pipeline" / "recon" / "state_expansion_render_probe_sos_2026_05_01.json"
OUT_JSON = ROOT / "pipeline" / "recon" / "state_expansion_qc_2026_05_01.json"
OUT_MD = ROOT / "pipeline" / "recon" / "state_expansion_qc_2026_05_01.md"
DOCS_MD = ROOT / "docs" / "state-expansion-qc-2026-05-01.md"


READY_REQUIRED = {
    "listing_url",
    "sample_urls",
    "cms_family",
    "content_shapes",
    "listing_selectors",
    "detail_selectors",
    "pagination",
    "attribution_mode",
}


def load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def main() -> None:
    rows = load_json(INVENTORY)
    broad = load_json(BROAD_RENDER)
    sos = load_json(SOS_RENDER)

    status_counts = Counter(r.get("implementation_status") for r in rows)
    row_kind_counts = Counter(r.get("row_kind") for r in rows)
    url_type_counts = Counter(r.get("listing_url_type") for r in rows)
    office_counts = Counter(r.get("office_scope") for r in rows)

    duplicate_urls: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        url = row.get("listing_url")
        if url and url != "UNKNOWN_NEEDS_PROFILE":
            duplicate_urls[url].append(row["source_id"])
    duplicate_urls = {url: ids for url, ids in duplicate_urls.items() if len(ids) > 1}

    readiness_issues = []
    for row in rows:
        if row.get("implementation_status") != "ready_first_wave":
            continue
        missing = []
        for field in READY_REQUIRED:
            value = row.get(field)
            if value in (None, "", [], "unknown", ["needs profile"], "needs profile"):
                missing.append(field)
        if row.get("listing_url_type") not in {"press_listing", "central_press_listing"}:
            missing.append("listing_url_type:not_press_listing")
        evidence = row.get("evidence") or {}
        if evidence.get("probe_status") != "ok":
            missing.append("evidence.probe_status")
        if missing:
            readiness_issues.append({"source_id": row["source_id"], "missing_or_weak": missing})

    placeholder_count = sum(1 for r in rows if r.get("row_kind") == "gap_placeholder")
    office_base_count = sum(1 for r in rows if r.get("listing_url_type") == "office_base_url")
    broad_deltas = [r for r in broad if r.get("material_render_delta")]
    sos_deltas = [r for r in sos if r.get("material_render_delta")]

    qc = {
        "generated": date.today().isoformat(),
        "row_count": len(rows),
        "status_counts": dict(status_counts),
        "row_kind_counts": dict(row_kind_counts),
        "listing_url_type_counts": dict(url_type_counts),
        "office_scope_counts": dict(office_counts),
        "duplicate_non_placeholder_urls": duplicate_urls,
        "ready_readiness_issues": readiness_issues,
        "gap_placeholder_count": placeholder_count,
        "office_base_url_count": office_base_count,
        "broad_render_count": len(broad),
        "broad_render_material_deltas": len(broad_deltas),
        "sos_render_count": len(sos),
        "sos_render_material_deltas": len(sos_deltas),
        "sos_render_errors": [r for r in sos if r.get("render_status") != "ok"],
    }
    OUT_JSON.write_text(json.dumps(qc, indent=2, ensure_ascii=False) + "\n")

    lines = [
        "# State Expansion QC",
        "",
        f"Generated: {qc['generated']}",
        "",
        f"- Inventory rows: {qc['row_count']}",
        f"- Gap placeholders: {placeholder_count}",
        f"- Directory/base office rows: {office_base_count}",
        f"- Duplicate non-placeholder URLs: {len(duplicate_urls)}",
        f"- Ready-row readiness issues: {len(readiness_issues)}",
        f"- Broad render probe rows: {len(broad)}; material deltas: {len(broad_deltas)}",
        f"- SOS render probe rows: {len(sos)}; material deltas: {len(sos_deltas)}",
        "",
        "## Status Counts",
        "",
    ]
    for key, value in sorted(status_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Row Kinds", ""])
    for key, value in sorted(row_kind_counts.items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Listing URL Types", ""])
    for key, value in sorted(url_type_counts.items()):
        lines.append(f"- `{key}`: {value}")
    if readiness_issues:
        lines.extend(["", "## Readiness Issues", ""])
        for issue in readiness_issues:
            lines.append(f"- `{issue['source_id']}`: {', '.join(issue['missing_or_weak'])}")
    if duplicate_urls:
        lines.extend(["", "## Duplicate Non-Placeholder URLs", ""])
        for url, ids in duplicate_urls.items():
            lines.append(f"- {url}: {', '.join(ids)}")
    lines.append("")
    rendered = "\n".join(lines)
    OUT_MD.write_text(rendered)
    DOCS_MD.write_text(rendered)


if __name__ == "__main__":
    main()
