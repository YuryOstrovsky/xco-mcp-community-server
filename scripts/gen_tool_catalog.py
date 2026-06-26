#!/usr/bin/env python3
"""Regenerate docs/TOOL_CATALOG.md from generated/mcp_tools.json.

The MCP server serves docs/TOOL_CATALOG.md as-is (GET /docs/tools); it does not
regenerate it. Run this after changing the tool catalog so the doc stays in sync:

    python3 scripts/gen_tool_catalog.py

Paths are resolved relative to the repo root, so it works from any directory.
"""
from __future__ import annotations

import json
from collections import Counter, OrderedDict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_JSON = ROOT / "generated" / "mcp_tools.json"
OUT_MD = ROOT / "docs" / "TOOL_CATALOG.md"


def tier_of(t: dict) -> str:
    return "tier2" if "tier2" in (t.get("tags") or []) else "tier1"


def endpoint_str(t: dict) -> str:
    ep = t.get("endpoint")
    if not ep:
        return ""
    return f"{ep.get('host', '')}{ep.get('path', '')}"


def prop_type(p: dict) -> str:
    if "type" in p:
        return p["type"]
    if "oneOf" in p:
        return "|".join(sub.get("type", "?") for sub in p["oneOf"])
    return "?"


def trunc(d: str, n: int = 220) -> str:
    d = (d or "").replace("\n", " ").strip()
    return d if len(d) <= n else d[: n - 1] + "…"


def main() -> None:
    cat = json.loads(CATALOG_JSON.read_text(encoding="utf-8"))
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    tier_counts = Counter(tier_of(t) for t in cat)
    risk_counts = Counter((t.get("policy") or {}).get("risk", "") for t in cat)
    cat_counts = Counter(t.get("category", "") for t in cat)

    # category order: alphabetical, with restconf last
    cats = sorted(c for c in cat_counts if c and c != "restconf")
    if "restconf" in cat_counts:
        cats.append("restconf")

    out: list[str] = []
    out.append("# MCP Tool Catalog")
    out.append("")
    out.append(f"_Generated from `mcp_tools.json` on {date}_")
    out.append("")
    out.append("## Summary")
    out.append(f"- Total tools: **{len(cat)}**")
    out.append("- By tier: " + ", ".join(
        f"**{k}**={tier_counts[k]}" for k in ("tier1", "tier2") if tier_counts[k]))
    out.append("- By risk: " + ", ".join(
        f"**{k}**={v}" for k, v in sorted(risk_counts.items())))
    out.append("")
    out.append("## Categories")
    for c in cats:
        out.append(f"- **{c}**: {cat_counts[c]}")
    out.append("")
    out.append("---")
    out.append("")

    by_cat: "OrderedDict[str, list]" = OrderedDict((c, []) for c in cats)
    for t in cat:
        by_cat.setdefault(t.get("category", ""), []).append(t)

    for c in cats:
        out.append(f"## {c}")
        out.append("")
        for t in sorted(by_cat[c], key=lambda x: x.get("name", "")):
            pol = t.get("policy") or {}
            out.append(f"### `{t.get('name', '')}`")
            out.append(f"- Tier: **{tier_of(t)}**  ")
            out.append(f"- Method: **{t.get('method', '')}**  ")
            out.append(f"- Endpoint: `{endpoint_str(t)}`  ")
            out.append(
                f"- Risk: **{pol.get('risk', '')}**, "
                f"auto_mode: **{pol.get('allowed_in_auto_mode', '')}**, "
                f"confirm: **{pol.get('requires_confirmation', '')}**"
            )
            out.append("")
            out.append(f"> {trunc(t.get('description', ''))}")
            out.append("")
            schema = t.get("input_schema") or {}
            props = schema.get("properties") or {}
            required = set(schema.get("required") or [])
            if props:
                out.append("**Inputs**")
                out.append("")
                out.append("| name | type | required | default | description |")
                out.append("|---|---|---:|---|---|")
                for pname, p in props.items():
                    default = p.get("default", "")
                    desc = (p.get("description", "") or "").replace("\n", " ").replace("|", "\\|")
                    req = "yes" if pname in required else "no"
                    ptype = prop_type(p).replace("|", "\\|")
                    out.append(f"| `{pname}` | `{ptype}` | {req} | `{default}` | {desc} |")
                out.append("")
            tags = ", ".join(f"`{tg}`" for tg in (t.get("tags") or []))
            out.append(f"- Tags: {tags}")
            out.append("")

    text = "\n".join(out).rstrip() + "\n"
    OUT_MD.write_text(text, encoding="utf-8")
    print(f"wrote {OUT_MD.relative_to(ROOT)}: {len(cat)} tools, "
          f"tiers={dict(tier_counts)}, categories={len(cats)}")


if __name__ == "__main__":
    main()
