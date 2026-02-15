#!/usr/bin/env python3
"""
Matrix bot that exports field-notes channel content to JSON for publishing.

Usage:
  python bot.py export              # Fetch history, export, write to output dir
  python bot.py run                # Stay online, export on !export command (optional)

Requires MATRIX_HOMESERVER, MATRIX_USER, MATRIX_PASSWORD (or MATRIX_ACCESS_TOKEN),
MATRIX_ROOM_ID, and OUTPUT_DIR in environment or .env file.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))

from nio import (
    AsyncClient,
    LoginError,
    RoomMessageText,
    RoomMessagesError,
    RoomMessagesResponse,
    RoomResolveAliasError,
    RoomResolveAliasResponse,
)

from export import process_messages

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load config from env. Supports .env file if python-dotenv is installed."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    def _get(key: str, default: str = "") -> str:
        v = os.getenv(key) or ""
        return v.strip() or default

    return {
        "homeserver": _get("MATRIX_HOMESERVER", "https://matrix.campaignlab.uk"),
        "user": _get("MATRIX_USER"),
        "password": _get("MATRIX_PASSWORD"),
        "access_token": _get("MATRIX_ACCESS_TOKEN"),
        "room_id": _get("MATRIX_ROOM_ID"),
        "output_dir": Path(_get("OUTPUT_DIR") or str(BASE_DIR)),
        "store_path": Path(_get("MATRIX_STORE_PATH") or str(BASE_DIR / ".matrix_store")),
    }


def event_to_message(event: dict, room_id: str = "") -> dict:
    """Convert Matrix client API event to format expected by clean_export."""
    ev = event if isinstance(event, dict) else getattr(event, "source", {})
    if not isinstance(ev, dict):
        ev = {}
    return {
        "type": ev.get("type", "m.room.message"),
        "event_id": ev.get("event_id"),
        "sender": ev.get("sender"),
        "origin_server_ts": ev.get("origin_server_ts", 0),
        "room_id": ev.get("room_id") or room_id,
        "content": ev.get("content", {}),
        "unsigned": ev.get("unsigned", {}),
    }


async def fetch_room_messages(client: AsyncClient, room_id: str) -> list:
    """Paginate through room history and collect all events."""
    messages = []
    start = "END"  # Start from latest, paginate backward

    while True:
        resp = await client.room_messages(room_id, start=start, limit=100, direction="b")
        if isinstance(resp, RoomMessagesError):
            logger.error("RoomMessagesError: %s", resp.message)
            break

        if not isinstance(resp, RoomMessagesResponse):
            break

        chunk = resp.chunk
        if not chunk:
            break

        for event in chunk:
            ev = getattr(event, "source", event)
            if isinstance(ev, dict) and ev.get("type") == "m.room.message":
                messages.append(event_to_message(ev, room_id))

        start = resp.end
        if not start:
            break

        logger.info("Fetched %d events so far...", len(messages))

    # API returns newest first when direction=b; we want chronological (oldest first)
    messages.sort(key=lambda m: m.get("origin_server_ts", 0))
    return messages


async def resolve_room_id(client: AsyncClient, room_id: str) -> str:
    """Resolve room alias (#name:server) to room id (!xxx:server)."""
    if room_id.startswith("!"):
        return room_id
    if not room_id.startswith("#"):
        return room_id
    resp = await client.room_resolve_alias(room_id)
    if isinstance(resp, RoomResolveAliasError):
        logger.warning("Could not resolve alias %s: %s", room_id, resp.message)
        return room_id
    return resp.room_id


async def do_export(client: AsyncClient, config: dict) -> bool:
    """Fetch room history and export to JSON."""
    room_id = await resolve_room_id(client, config["room_id"])
    config["room_id"] = room_id  # cache for next call
    output_dir = config["output_dir"]
    output_path = output_dir / "content.json"

    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Fetching messages from room %s...", room_id)
    messages = await fetch_room_messages(client, room_id)
    logger.info("Fetched %d total events", len(messages))

    existing = None
    if output_path.exists():
        try:
            with open(output_path, encoding="utf-8") as f:
                existing = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    out = process_messages(messages, existing_export=existing)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)

    logger.info(
        "Exported to %s: %d messages (%d roots + replies)",
        output_path,
        len(out["messages"]),
        len(out["processed_ids"]),
    )
    return True


async def main_export(config: dict) -> None:
    """One-shot export: login, fetch, export, logout."""
    client = AsyncClient(
        config["homeserver"],
        config["user"],
        store_path=str(config["store_path"]),
    )

    if config.get("access_token"):
        client.access_token = config["access_token"]
        client.user_id = config["user"] or os.getenv("MATRIX_USER_ID", "")
    else:
        if not config.get("password"):
            logger.error("Need MATRIX_PASSWORD or MATRIX_ACCESS_TOKEN")
            return
        resp = await client.login(config["password"])
        if isinstance(resp, LoginError):
            logger.error("Login failed: %s", resp.message)
            return

    try:
        await do_export(client, config)
    finally:
        await client.close()


async def main_run(config: dict) -> None:
    """Daemon mode: sync and run export on !export command."""
    client = AsyncClient(
        config["homeserver"],
        config["user"],
        store_path=str(config["store_path"]),
    )

    if config.get("access_token"):
        client.access_token = config["access_token"]
        client.user_id = config["user"] or os.getenv("MATRIX_USER_ID", "")
    else:
        resp = await client.login(config["password"])
        if isinstance(resp, LoginError):
            logger.error("Login failed: %s", resp.message)
            return

    async def on_room_message(room, event):
        """Handle !export command."""
        if not isinstance(event, RoomMessageText) or not event.body:
            return
        if event.body.strip().lower() != "!export":
            return
        logger.info("Export requested by %s", event.sender)
        await do_export(client, config)
        await client.room_send(
            room_id=room.room_id,
            message_type="m.room.message",
            content={"msgtype": "m.text", "body": "Export complete. Check the repo."},
        )

    client.add_event_callback(on_room_message, RoomMessageText)

    config["room_id"] = await resolve_room_id(client, config["room_id"])
    logger.info("Bot running. Send !export in the room to trigger export.")
    await client.sync_forever(30000)


def main():
    config = load_config()

    if not config["room_id"]:
        logger.error("Set MATRIX_ROOM_ID (room id or alias like #field-notes:matrix.campaignlab.uk)")
        sys.exit(1)

    mode = (sys.argv[1] if len(sys.argv) > 1 else "export").lower()
    if mode == "run":
        asyncio.run(main_run(config))
    else:
        asyncio.run(main_export(config))


if __name__ == "__main__":
    main()
