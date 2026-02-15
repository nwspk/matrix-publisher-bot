#!/usr/bin/env python3
"""
Clean Matrix channel export.json to a minimal schema for publishing.

Output format:
  {
    "messages": [ ... ],
    "processed_ids": [ "event_id", ... ],
    "last_processed_ts": 1771110622252
  }

Types: journal (short reading notes), link, question, idea, project, field_note, blog_post, reply
- Link-only posts → type "link" (even if posted with 📥)
- Reading with substantive text → type "journal"
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Emoji → type mapping (reading → journal for posts with text; link-only overridden to link)
EMOJI_TO_TYPE = {
    "📥": "journal",  # short reading notes; link-only gets overridden to "link"
    "🔗": "link",
    "❓": "question",
    "💾": "project",
    "💡": "idea",
    "📔": "field_note",
    "📄": "blog_post",
}

CATEGORY_EMOJIS = list(EMOJI_TO_TYPE.keys())


def extract_keywords(body: str) -> list:
    """
    Extract keywords for sorting. Supports:
    - keywords: ai, governance, research (comma-separated)
    - #tag1 #tag2
    - **bold** phrases (auto-extract)
    """
    keywords = []
    body = body or ""

    # Explicit keywords line
    m = re.search(r"keywords?\s*:\s*([^\n#]+)", body, re.I)
    if m:
        keywords.extend([w.strip().lower() for w in m.group(1).split(",") if w.strip()])

    # Hashtags
    keywords.extend(re.findall(r"#(\w[\w\-]*)", body))

    # **Bold** phrases (2–4 words)
    for m in re.finditer(r"\*\*([^*]+)\*\*", body):
        phrase = m.group(1).strip()
        if 2 <= len(phrase.split()) <= 4 and phrase.lower() not in [k.lower() for k in keywords]:
            keywords.append(phrase)

    return list(dict.fromkeys(keywords))[:15]  # Dedupe, limit 15


def get_message_content(msg: dict) -> tuple[str, str]:
    """Extract (body, formatted_body) from a message. formatted_body may be empty."""
    content = msg.get("content") or {}
    body = content.get("body") or ""
    formatted_body = content.get("formatted_body") or ""
    return body, formatted_body


def is_link_only(body: str) -> bool:
    """True if the post is essentially just a URL or citation (no substantive prose)."""
    # Strip metadata and emoji
    body = re.sub(r"_\s*originally posted[^_]*_", "", body, flags=re.I)
    body = re.sub(r"originally posted[^\n]*", "", body, flags=re.I)
    for emoji in CATEGORY_EMOJIS:
        body = body.replace(emoji + "\uFE0F", "").replace(emoji, "")  # variant first, then base
    body = body.strip()
    # Single markdown link [title](url) or bare URL = link
    if re.match(r"^\s*\[([^\]]*)\]\(https?://[^\)]+\)\s*$", body):
        return True
    if re.match(r"^\s*https?://\S+\s*$", body):
        return True
    # Remove URLs; if little prose left, it's link-only
    without_urls = re.sub(r"https?://[^\s\)\]]+", "", body)
    without_urls = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", without_urls)  # [text](url) → text
    without_urls = re.sub(r"\s+", " ", without_urls).strip()
    return len(without_urls) < 100


def is_category_post(msg: dict) -> bool:
    """Check if a message is a root post in one of the publishable categories."""
    if msg.get("type") != "m.room.message":
        return False
    content = msg.get("content") or {}
    # Skip edits (m.replace) and thread replies - we only want root posts
    relates_to = content.get("m.relates_to") or {}
    if relates_to.get("rel_type") == "m.replace":
        return False
    if relates_to.get("rel_type") == "m.thread":
        return False
    body, _ = get_message_content(msg)
    body = body.lstrip()
    # Strip leading markdown (#, -, *, etc.) so "### 📔 Field Note" matches
    body_normalized = re.sub(r"^[\s#\-*]+", "", body)
    return any(body_normalized.startswith(emoji) for emoji in CATEGORY_EMOJIS)


def get_message_type(msg: dict, is_reply: bool) -> str:
    """Map message to type: journal, link, question, etc., or 'reply'."""
    if is_reply:
        return "reply"
    body, _ = get_message_content(msg)
    body = body.lstrip()
    body_normalized = re.sub(r"^[\s#\-*]+", "", body)
    for emoji, t in EMOJI_TO_TYPE.items():
        if body_normalized.startswith(emoji) or body_normalized.startswith(emoji + "\uFE0F"):
            if t == "journal" and is_link_only(body):
                return "link"
            return t
    return "field_note"  # fallback for matched-but-unusual format


def get_parent_id(msg: dict) -> str | None:
    """For replies, return the parent message id (from m.thread or m.in_reply_to)."""
    content = msg.get("content") or {}
    relates_to = content.get("m.relates_to") or {}
    if relates_to.get("rel_type") == "m.thread":
        return relates_to.get("event_id")
    in_reply = relates_to.get("m.in_reply_to") or content.get("m.in_reply_to")
    if isinstance(in_reply, dict) and in_reply.get("event_id"):
        return in_reply["event_id"]
    return None


def build_edit_map(messages: list) -> dict:
    """Build original_id -> (body, formatted_body) for the latest edit of each message."""
    edits = {}  # original_id -> (body, formatted_body)
    for msg in messages:
        if msg.get("type") != "m.room.message":
            continue
        content = msg.get("content") or {}
        relates_to = content.get("m.relates_to") or {}
        if relates_to.get("rel_type") != "m.replace":
            continue
        original_id = relates_to.get("event_id")
        if not original_id:
            continue
        new_content = content.get("m.new_content") or content
        body = new_content.get("body") or ""
        formatted_body = new_content.get("formatted_body") or ""
        edits[original_id] = (body, formatted_body)
    return edits


def to_minimal_message(msg: dict, is_reply: bool, edit_map: dict) -> dict:
    """Convert a Matrix message to the minimal schema."""
    eid = msg.get("event_id")
    ts = msg.get("origin_server_ts", 0)
    msg_type = get_message_type(msg, is_reply)
    parent_id = get_parent_id(msg) if is_reply else None

    body, formatted_body = get_message_content(msg)
    if eid in edit_map:
        body, formatted_body = edit_map[eid]

    out = {
        "id": eid,
        "ts": ts,
        "type": msg_type,
        "body": body,
        "parent_id": parent_id,
    }
    if formatted_body:
        out["formatted_body"] = formatted_body
    # Keywords for root posts (helps with sorting/filtering)
    if not is_reply:
        kw = extract_keywords(body)
        if kw:
            out["keywords"] = kw
    return out


def process_messages(
    messages: list,
    existing_export: dict | None = None,
) -> dict:
    """Filter messages to minimal schema. Used by both file-based export and bot."""
    already_processed = set()
    existing_messages = []
    existing_last_ts = 0
    if existing_export:
        already_processed = set(existing_export.get("processed_ids") or [])
        existing_messages = existing_export.get("messages") or []
        existing_last_ts = existing_export.get("last_processed_ts") or 0
        new_only = [m for m in messages if m.get("event_id") not in already_processed]
        # Keep existing roots so we can attach new replies to their threads
        existing_root_ids = {m["id"] for m in existing_messages if not m.get("parent_id")}
    else:
        new_only = messages
        existing_root_ids = set()

    category_root_ids = set(existing_root_ids)
    for msg in new_only:
        if is_category_post(msg):
            eid = msg.get("event_id")
            if eid:
                category_root_ids.add(eid)

    keep_ids = set(category_root_ids)
    for msg in new_only:
        if msg.get("type") != "m.room.message":
            continue
        root_id = get_parent_id(msg)
        if root_id and root_id in category_root_ids:
            keep_ids.add(msg.get("event_id"))

    changed = True
    while changed:
        changed = False
        for msg in new_only:
            if msg.get("type") != "m.room.message":
                continue
            eid = msg.get("event_id")
            if eid in keep_ids:
                continue
            parent_id = get_parent_id(msg)
            if parent_id and parent_id in keep_ids:
                keep_ids.add(eid)
                changed = True

    kept = [m for m in new_only if m.get("event_id") in keep_ids]
    kept.sort(key=lambda m: m.get("origin_server_ts", 0))

    edit_map = build_edit_map(messages)  # use full list for edit resolution

    minimal_new = []
    for m in kept:
        eid = m.get("event_id")
        is_reply = eid not in category_root_ids
        minimal_new.append(to_minimal_message(m, is_reply, edit_map))

    if existing_messages:
        all_messages = existing_messages + minimal_new
        all_messages.sort(key=lambda m: m.get("ts", 0))
        minimal = all_messages
        processed_ids = sorted(already_processed | keep_ids)
    else:
        minimal = minimal_new
        processed_ids = sorted(keep_ids)

    last_processed_ts = max(
        [m.get("origin_server_ts", 0) for m in kept] + [existing_last_ts],
        default=0,
    )

    return {
        "messages": minimal,
        "processed_ids": processed_ids,
        "last_processed_ts": last_processed_ts,
    }


def clean_export(input_path: str, output_path: str, incremental: bool = False) -> None:
    """Filter export to minimal schema: category posts and their threads."""
    with open(input_path, encoding="utf-8") as f:
        data = json.load(f)

    messages = data.get("messages", [])

    existing = None
    if incremental and Path(output_path).exists():
        try:
            with open(output_path, encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("processed_ids"):
                print(f"  Incremental: {len(existing['processed_ids'])} already processed")
        except (json.JSONDecodeError, OSError):
            pass

    out = process_messages(messages, existing_export=existing)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    print(f"Wrote {output_path}")
    print(f"  Original: {len(messages)} → {len(out['messages'])} messages")
    print(f"  processed_ids: {len(out['processed_ids'])}, last_processed_ts: {out['last_processed_ts']}")


def review_types(cleaned_path: str) -> None:
    """Print root messages with id, type, and body preview for manual review."""
    with open(cleaned_path, encoding="utf-8") as f:
        data = json.load(f)
    for m in data.get("messages") or []:
        if m.get("parent_id"):
            continue
        body = (m.get("body") or "")[:80].replace("\n", " ").rstrip()
        suffix = "..." if len(m.get("body") or "") > 80 else ""
        print(f"{m['id']}\t{m['type']}\t{body}{suffix}")


def main():
    base = Path(__file__).parent
    input_path = base / "export.json"
    output_path = base / "content.json"
    incremental = False

    args = sys.argv[1:]
    if "--review" in args:
        args = [a for a in args if a != "--review"]
        target = args[0] if args else str(base / "content.json")
        review_types(target)
        return
    if "--incremental" in args:
        incremental = True
        args = [a for a in args if a != "--incremental"]
    if args:
        input_path = Path(args[0])
    if len(args) > 1:
        output_path = Path(args[1])

    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    clean_export(str(input_path), str(output_path), incremental=incremental)


if __name__ == "__main__":
    main()
