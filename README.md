# Field Notes Bot

A Matrix bot that exports a field-notes channel to a minimal JSON schema (`content.json`) for publishing elsewhere -- blog, CMS, static site, etc.

## How it works

1. Connects to a Matrix room and fetches the full message history
2. Keeps only emoji-tagged root posts and their thread replies
3. Maps each post to a type (`journal`, `link`, `field_note`, etc.) based on its leading emoji
4. Validates the output and excludes items with data issues
5. Writes `content.json` -- a flat list of messages ready for your publishing pipeline

## Quick start

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your credentials
python bot.py export
```

### Configuration

Set these in `.env` (or as environment variables):

| Variable | Required | Description |
|----------|----------|-------------|
| `MATRIX_HOMESERVER` | | Homeserver URL (default: `https://matrix.campaignlab.uk`) |
| `MATRIX_USER` | yes | Bot user id (`@bot:server`) |
| `MATRIX_PASSWORD` | yes* | Bot password |
| `MATRIX_ACCESS_TOKEN` | yes* | Or use a token instead of password |
| `MATRIX_ROOM_ID` | yes | Room id (`!xxx:server`) or alias (`#name:server`) |
| `OUTPUT_DIR` | | Where to write `content.json` (default: this repo) |

\* Provide either `MATRIX_PASSWORD` or `MATRIX_ACCESS_TOKEN`.

### Running

```bash
python bot.py export   # one-shot: fetch history, write content.json, exit
python bot.py run      # daemon: stay online, export on !export command in the room
```

## Output schema

`content.json` contains:

```json
{
  "messages": [
    {
      "id": "$event_id",
      "ts": 1771110622252,
      "type": "journal",
      "body": "📥 Notes on ...",
      "formatted_body": "<p>📥 Notes on ...</p>",
      "parent_id": null,
      "keywords": ["governance", "ai"]
    }
  ],
  "processed_ids": ["$event_id", "..."],
  "last_processed_ts": 1771110622252
}
```

**Types:** `journal`, `link`, `question`, `idea`, `project`, `field_note`, `blog_post`, `reply`

Incremental exports merge new messages into the existing file using `processed_ids` and `last_processed_ts`.

## Channel guidelines

Start each post with an emoji so the bot classifies it correctly.

| Emoji | Type | Use for |
|-------|------|---------|
| 🔗 | link | Bare URL or `[title](url)` with no extra prose |
| 📥 | journal | Short reading notes -- lists, quotes, brief reflections |
| 📔 | field_note | Longer reflections, analysis, "Field Note:" posts |
| 💡 | idea | Ideas, brainstorms |
| 💾 | project | Tools, apps, projects you're tracking |
| ❓ | question | Questions to explore |
| 📄 | blog_post | Finished posts ready to publish |

- **Links vs journal:** Use 🔗 for bare links. If you add more than a short caption, use 📥.
- **Journal vs field note:** 📥 for short notes; 📔 for longer reflective pieces.

### Keywords (optional)

Add keywords to help sort and filter:

```
keywords: ai, governance, research
#ai #governance
```

Bold phrases (`**like this**`) are also auto-extracted as keywords.

### Examples

```
🔗 https://example.com/article
📥 Homework from Matt -- tell me 1 thing from each section
📔 Field Note: On the legitimacy of the governance module
keywords: governance, legitimacy
💡 An app that forwards newsletters to this channel
#automation #newsletters
```

## GitHub Actions

The included workflow (`.github/workflows/export.yml`) runs the full pipeline automatically:

- **Daily** at 6 AM UTC
- **Manually** from the Actions tab

**Setup:** Add repo secrets (Settings > Secrets and variables > Actions):

| Secret | Required | Description |
|--------|----------|-------------|
| `MATRIX_USER` | yes | Bot user id |
| `MATRIX_PASSWORD` | yes* | Bot password |
| `MATRIX_ACCESS_TOKEN` | yes* | Or use token instead |
| `MATRIX_ROOM_ID` | yes | Room id or alias |
| `MATRIX_HOMESERVER` | | Defaults to `https://matrix.campaignlab.uk` |

**Pipeline:** export > validate > exclude flagged items > open GitHub issue if needed > commit clean `content.json`.

## Integrating with another project

Point `OUTPUT_DIR` to a path in your target repo:

```bash
OUTPUT_DIR=../your-blog/data python bot.py export
```

Or run on a cron:

```bash
0 * * * * cd /path/to/field-notes-bot && python bot.py export
```

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Matrix bot -- connects, fetches history, writes `content.json` |
| `export.py` | Core logic -- filters, classifies, and transforms messages |
| `validate_export.py` | Validates output and excludes flagged items |
