#!/usr/bin/env python3
"""
Validate content.json. Flags items with data issues.

Returns exit 0 if clean, exit 1 if issues found.
Writes validation report to validation_report.json (for workflow to use).
"""

import json
import sys
from pathlib import Path


def validate_message(msg: dict, is_root: bool) -> list[str]:
    """Return list of issue codes for this message. Empty = no issues."""
    issues = []
    body = (msg.get("body") or "").strip()
    body_len = len(body)

    if is_root:
        has_url = "http://" in body or "https://" in body
        if body_len < 25 and not has_url:
            issues.append("empty_or_minimal")
        if body_len > 0 and body_len < 100 and not any(c.isalpha() for c in body):
            issues.append("no_substantive_text")
        # Suspicious encoding
        if "\ufffd" in body or body.endswith("\\"):
            issues.append("possible_encoding_issue")

    return issues


def validate_export(export_path: Path) -> tuple[list, list]:
    """
    Validate export. Returns (valid_messages, flagged_items).
    flagged_items: list of {id, type, body_preview, issues}
    """
    with open(export_path, encoding="utf-8") as f:
        data = json.load(f)

    messages = data.get("messages", [])
    valid = []
    flagged = []

    for m in messages:
        is_root = not m.get("parent_id")
        issues = validate_message(m, is_root)

        if issues:
            flagged.append({
                "id": m.get("id"),
                "type": m.get("type"),
                "body_preview": (m.get("body") or "")[:120].replace("\n", " "),
                "issues": issues,
            })
        else:
            valid.append(m)

    return valid, flagged


def main():
    base = Path(__file__).parent
    export_path = base / "content.json"
    report_path = base / "validation_report.json"

    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = [a for a in sys.argv[1:] if a.startswith("-")]
    if args:
        export_path = Path(args[0])
    if len(args) > 1:
        report_path = Path(args[1])

    if not export_path.exists():
        print(f"Error: {export_path} not found", file=sys.stderr)
        sys.exit(2)

    with open(export_path, encoding="utf-8") as f:
        data = json.load(f)

    valid, flagged = validate_export(export_path)

    report = {
        "total": len(valid) + len(flagged),
        "valid_count": len(valid),
        "flagged_count": len(flagged),
        "flagged": flagged,
    }

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    if flagged:
        print(f"Validation: {len(flagged)} item(s) flagged, {len(valid)} clean")
        for item in flagged[:5]:
            print(f"  - {item['id'][:20]}... {item['issues']}: {item['body_preview'][:50]}...")
        if len(flagged) > 5:
            print(f"  ... and {len(flagged) - 5} more")

        # Rewrite export excluding flagged items (so clean data gets committed)
        flagged_ids = {f["id"] for f in flagged}
        data["messages"] = valid
        data["processed_ids"] = [i for i in (data.get("processed_ids") or []) if i not in flagged_ids]
        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Excluded {len(flagged)} items from export")

        sys.exit(1)

    print(f"Validation: all {len(valid)} items clean")
    sys.exit(0)


if __name__ == "__main__":
    main()
