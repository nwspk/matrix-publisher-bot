# Matrix Publisher Bot

A template for Newspeak House fellows to publish field notes from a Matrix channel to the [fellowship website](https://2025.newspeak.house). Each fellow gets their own repo, their own export, and their own `content.json` that the site pulls in at build time.

## How it works

1. Connects to your Matrix field-notes channel and fetches the full message history
2. Keeps only emoji-tagged root posts and their thread replies
3. Maps each post to a type (`journal`, `link`, `field_note`, etc.) based on its leading emoji
4. Auto-extracts keywords from your text using [YAKE](https://github.com/LIAAD/yake)
5. Validates the output and excludes items with data issues
6. Commits `content.json` to your repo -- the site picks it up at build time

## Getting started

### 1. Create your repo

Click **"Use this template"** on GitHub to create your own copy (e.g. `nwspk/yourname-field-notes`).

### 2. Add repo secrets

Go to Settings > Secrets and variables > Actions and add:

| Secret | Required | Description |
|--------|----------|-------------|
| `MATRIX_USER` | yes | Bot user id (`@bot:server`) |
| `MATRIX_PASSWORD` | yes* | Bot password |
| `MATRIX_ACCESS_TOKEN` | yes* | Or use a token instead of password |
| `MATRIX_ROOM_ID` | yes | Your field-notes room id or alias |
| `MATRIX_HOMESERVER` | | Default: `https://matrix.campaignlab.uk` |
| `SITE_REPO` | | Site repo to rebuild (e.g. `nwspk/2025.newspeak.house`) |
| `SITE_DEPLOY_TOKEN` | | GitHub PAT with repo dispatch access |

\* Provide either `MATRIX_PASSWORD` or `MATRIX_ACCESS_TOKEN`.

The `SITE_REPO` and `SITE_DEPLOY_TOKEN` secrets are optional -- when set, the workflow will trigger a rebuild of the fellowship site after each export so your new posts appear automatically.

### 3. Run the export

The workflow runs **daily at 6 AM UTC** and can also be triggered manually from the Actions tab.

To test locally:

```bash
pip install -r requirements.txt
cp .env.example .env   # fill in your credentials
python bot.py export
```

### 4. Your data URL

Once the first export runs, your `content.json` is available at:

```
https://raw.githubusercontent.com/nwspk/yourname-field-notes/main/content.json
```

The fellowship site fetches this URL at build time to display your posts.

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

### Keywords

Keywords are **auto-extracted** from your post text -- no need to add them manually. You can also include `#hashtags` anywhere in a post and they'll be merged with the auto-extracted keywords.

### Examples

```
🔗 https://example.com/article
📥 Homework from Matt -- tell me 1 thing from each section
📔 Field Note: On the legitimacy of the governance module
💡 An app that forwards newsletters to this channel #automation
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
      "keywords": ["civic tech", "governance"]
    }
  ],
  "processed_ids": ["$event_id", "..."],
  "last_processed_ts": 1771110622252
}
```

**Types:** `journal`, `link`, `question`, `idea`, `project`, `field_note`, `blog_post`, `reply`

## Running modes

```bash
python bot.py export   # one-shot: fetch history, write content.json, exit
python bot.py run      # daemon: stay online, export on !export command
```

## Files

| File | Purpose |
|------|---------|
| `bot.py` | Matrix bot -- connects, fetches history, writes `content.json` |
| `export.py` | Core logic -- filters, classifies, and transforms messages |
| `validate_export.py` | Validates output and excludes flagged items |
