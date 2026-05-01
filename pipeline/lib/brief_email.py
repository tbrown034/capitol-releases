"""
HTML + plain-text rendering of a brief into a deliverable email.

The brief row carries the structured content; we render it once per send
with the per-subscriber unsubscribe token swapped in. Footer always carries
list-unsubscribe headers and the canonical link.
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Iterable


def _esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in (text or "").split("\n\n") if p.strip()]


def _fmt_date(brief_date: str) -> str:
    try:
        d = datetime.fromisoformat(brief_date)
        return d.strftime("%A, %B %-d, %Y")
    except Exception:
        return brief_date


def render_subject(brief: dict) -> str:
    return f"Capitol Brief: {brief['headline']}"


def render_html(
    brief: dict,
    *,
    citations_by_id: dict[str, dict],
    site_url: str,
    unsubscribe_url: str,
) -> str:
    bdate = _fmt_date(brief["brief_date"])
    out: list[str] = []

    out.append(f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(brief['headline'])}</title>
</head>
<body style="margin:0;padding:0;background:#f5f5f4;font-family:Georgia,'Source Serif Pro',serif;color:#171717;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f5f5f4;">
<tr><td align="center" style="padding:24px 12px;">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;background:#ffffff;border:1px solid #e5e5e5;">
<tr><td style="padding:28px 32px 8px 32px;">
<div style="font-family:'SF Mono',Menlo,monospace;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;color:#737373;">
  Capitol Brief &nbsp;/&nbsp; {_esc(bdate)}
</div>
</td></tr>
<tr><td style="padding:6px 32px 18px 32px;">
<h1 style="margin:0;font-size:28px;line-height:1.18;color:#171717;font-weight:normal;">{_esc(brief['headline'])}</h1>
""")

    if brief.get("dek"):
        out.append(
            f'<p style="margin:14px 0 0 0;font-size:16px;line-height:1.55;color:#404040;">{_esc(brief["dek"])}</p>'
        )

    out.append("</td></tr>")

    # Lede
    out.append('<tr><td style="padding:0 32px 18px 32px;">')
    for p in _paragraphs(brief.get("lede", "")):
        out.append(
            f'<p style="margin:0 0 14px 0;font-size:16px;line-height:1.7;color:#171717;">{_esc(p)}</p>'
        )
    out.append("</td></tr>")

    # Sections
    for sec in brief.get("sections") or []:
        out.append(
            '<tr><td style="padding:18px 32px 6px 32px;border-top:1px solid #e5e5e5;">'
            f'<h2 style="margin:0 0 12px 0;font-size:20px;line-height:1.25;color:#171717;font-weight:normal;">{_esc(sec.get("theme", ""))}</h2>'
        )
        for p in _paragraphs(sec.get("body", "")):
            out.append(
                f'<p style="margin:0 0 12px 0;font-size:15px;line-height:1.7;color:#262626;">{_esc(p)}</p>'
            )

        # Citation cards
        rids = sec.get("release_ids") or []
        cards = [citations_by_id.get(rid) for rid in rids]
        cards = [c for c in cards if c]
        if cards:
            out.append('<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="margin-top:6px;">')
            for c in cards:
                href = f"{site_url}/releases/{c['id']}"
                out.append(
                    '<tr><td style="padding:6px 10px;border:1px solid #e5e5e5;background:#fafafa;font-size:12px;line-height:1.5;color:#404040;">'
                    f'<a href="{_esc(href)}" style="color:#171717;text-decoration:none;">'
                    f'<strong>{_esc(c["senator_name"])}</strong> &middot; {_esc(c["party"])}-{_esc(c["state"])}<br>'
                    f'<span style="color:#525252;">{_esc(c["title"])}</span>'
                    "</a></td></tr>"
                    '<tr><td style="height:4px;line-height:4px;">&nbsp;</td></tr>'
                )
            out.append("</table>")

        out.append("</td></tr>")

    # Signals
    if brief.get("signals"):
        out.append(
            '<tr><td style="padding:18px 32px 8px 32px;border-top:1px solid #e5e5e5;">'
            '<h2 style="margin:0 0 12px 0;font-size:20px;line-height:1.25;color:#171717;font-weight:normal;">Signals</h2>'
        )
        for s in brief["signals"]:
            kind = (s.get("kind") or "").replace("_", " ")
            out.append(
                '<p style="margin:0 0 8px 0;font-size:14px;line-height:1.6;color:#404040;">'
                f'<span style="display:inline-block;background:#171717;color:#ffffff;font-size:10px;padding:2px 6px;border-radius:2px;text-transform:uppercase;letter-spacing:0.06em;font-family:Menlo,monospace;margin-right:8px;">{_esc(kind)}</span>'
                f'{_esc(s.get("note", ""))}</p>'
            )
        out.append("</td></tr>")

    # Quiet desks
    if brief.get("silent"):
        out.append(
            '<tr><td style="padding:18px 32px 8px 32px;border-top:1px solid #e5e5e5;">'
            '<h2 style="margin:0 0 8px 0;font-size:20px;line-height:1.25;color:#171717;font-weight:normal;">Quiet desks</h2>'
            '<p style="margin:0 0 10px 0;font-size:12px;color:#737373;">Senators with no release in two weeks or more.</p>'
            '<table role="presentation" cellpadding="0" cellspacing="0" width="100%">'
        )
        for s in brief["silent"]:
            days = s.get("days_quiet", 0)
            d_label = "—" if days >= 999 else f"{days}d"
            out.append(
                f'<tr><td style="font-size:13px;color:#525252;padding:4px 0;border-bottom:1px solid #f5f5f5;">{_esc(s.get("senator", ""))}</td>'
                f'<td align="right" style="font-size:12px;color:#737373;font-family:Menlo,monospace;padding:4px 0;border-bottom:1px solid #f5f5f5;">{_esc(d_label)}</td></tr>'
            )
        out.append("</table></td></tr>")

    # Footer
    out.append(
        '<tr><td style="padding:24px 32px 32px 32px;border-top:1px solid #e5e5e5;background:#fafafa;font-size:12px;line-height:1.6;color:#737373;">'
        f'<p style="margin:0 0 8px 0;">Synthesized by Anthropic\'s Claude Sonnet 4.6 from the day\'s collected senate.gov releases. Every claim links to the source record. The canonical archive is at <a href="{_esc(site_url)}/feed" style="color:#525252;">{_esc(site_url)}/feed</a>.</p>'
        f'<p style="margin:0 0 8px 0;">View this brief in browser: <a href="{_esc(site_url)}/brief/{_esc(brief["brief_date"])}" style="color:#525252;">{_esc(site_url)}/brief/{_esc(brief["brief_date"])}</a></p>'
        f'<p style="margin:12px 0 0 0;"><a href="{_esc(unsubscribe_url)}" style="color:#737373;">Unsubscribe</a> &middot; one click, no questions.</p>'
        "</td></tr>"
        "</table></td></tr></table></body></html>"
    )

    return "".join(out)


def render_text(
    brief: dict,
    *,
    citations_by_id: dict[str, dict],
    site_url: str,
    unsubscribe_url: str,
) -> str:
    lines: list[str] = []
    lines.append(f"CAPITOL BRIEF / {_fmt_date(brief['brief_date'])}")
    lines.append("=" * 60)
    lines.append("")
    lines.append(brief["headline"])
    lines.append("")
    if brief.get("dek"):
        lines.append(brief["dek"])
        lines.append("")

    for p in _paragraphs(brief.get("lede", "")):
        lines.append(p)
        lines.append("")

    for sec in brief.get("sections") or []:
        lines.append("-" * 60)
        lines.append(sec.get("theme", "").upper())
        lines.append("")
        for p in _paragraphs(sec.get("body", "")):
            lines.append(p)
            lines.append("")
        rids = sec.get("release_ids") or []
        for rid in rids:
            c = citations_by_id.get(rid)
            if c:
                lines.append(
                    f"  • {c['senator_name']} ({c['party']}-{c['state']}) — {c['title']}"
                )
                lines.append(f"    {site_url}/releases/{c['id']}")
        lines.append("")

    if brief.get("signals"):
        lines.append("-" * 60)
        lines.append("SIGNALS")
        lines.append("")
        for s in brief["signals"]:
            kind = (s.get("kind") or "").upper().replace("_", " ")
            lines.append(f"[{kind}] {s.get('note', '')}")
        lines.append("")

    if brief.get("silent"):
        lines.append("-" * 60)
        lines.append("QUIET DESKS (no release in 14+ days)")
        lines.append("")
        for s in brief["silent"]:
            days = s.get("days_quiet", 0)
            d = "—" if days >= 999 else f"{days}d"
            lines.append(f"  {s.get('senator', ''):42s} {d:>4s}")
        lines.append("")

    lines.append("=" * 60)
    lines.append(
        f"Synthesized by Claude Sonnet 4.6 from the day's senate.gov releases."
    )
    lines.append(f"View online: {site_url}/brief/{brief['brief_date']}")
    lines.append(f"Unsubscribe: {unsubscribe_url}")
    return "\n".join(lines)
