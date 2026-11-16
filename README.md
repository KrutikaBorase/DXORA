# Automated Multi-Platform Posting API

A small FastAPI service that publishes one short update to five platforms:

- Mastodon
- Bluesky
- Reddit
- Telegram
- Discord

Each platform is configured with environment variables. A platform without
credentials is reported as failed while the remaining platforms are still
attempted.

## Requirements

- Python 3.10 or newer
- API credentials for the platforms you want to use

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and add credentials for one or more platforms.
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

Interactive API documentation is available at
<http://localhost:4000/docs>.

## Request

`POST /posting` accepts one message with exactly one HTTP or HTTPS link. The
message, including the link, must be no longer than 200 characters.

```powershell
Invoke-RestMethod `
  -Uri http://localhost:4000/posting `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"message":"Check out our latest business platform: https://example.com"}'
```

## Response

```json
{
  "success": true,
  "results": [
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.social/@account/123",
      "public_access": true,
      "date": "2026-11-16",
      "time": "10:30:00",
      "error": null
    },
    {
      "platform": "Reddit",
      "status": "failed",
      "posted_url": null,
      "public_access": false,
      "date": null,
      "time": null,
      "error": "Reddit credentials and REDDIT_SUBREDDIT are not fully configured"
    }
  ]
}
```

`success` is true when at least one platform accepts the post. A successful
Telegram post can have no public URL because Telegram private chats do not
provide one.

## Proof of working

A live request was sent to `POST /posting` with the message
`Posting API demo: https://example.com`. Mastodon and Discord accepted the
post. Bluesky, Reddit and Telegram were intentionally left unconfigured, so they
were reported as failed without stopping the other platforms.

### Swagger UI request (`http://localhost:4000/docs`)

![Swagger request](docs/proof/swagger-request.png)

### Uvicorn running and JSON response with `posted_url`

![Terminal and JSON response](docs/proof/terminal-json-response.png)

Full response: [docs/proof/posting-response.json](docs/proof/posting-response.json)

```json
{
  "success": true,
  "results": [
    {
      "platform": "Mastodon",
      "status": "success",
      "posted_url": "https://mastodon.social/@krutika_01/117627523510635019",
      "public_access": true,
      "date": "2026-11-16",
      "time": "18:26:08",
      "error": null
    },
    {
      "platform": "Discord",
      "status": "success",
      "posted_url": "https://discord.com/channels/1571947972998987938/1571954547298144266",
      "public_access": true,
      "date": "2026-11-16",
      "time": "18:26:09",
      "error": null
    }
  ]
}
```

The response also contains `failed` entries for the unconfigured platforms
(see the full JSON file).

### Mastodon post

![Mastodon post](docs/proof/mastodon-post.png)

### Discord message

![Discord message](docs/proof/discord-message.png)

## Platform setup

Copy `.env.example` to `.env`. Only set credentials for platforms you intend
to use. Do not commit `.env` or access tokens.

Official API references:

- [Mastodon REST API](https://docs.joinmastodon.org/methods/statuses/)
- [Bluesky create session](https://docs.bsky.app/docs/api/com-atproto-server-create-session)
- [Bluesky create record](https://docs.bsky.app/docs/api/com-atproto-repo-create-record)
- [Reddit API submit](https://www.reddit.com/dev/api/#POST_api_submit)
- [Telegram Bot API sendMessage](https://core.telegram.org/bots/api#sendmessage)
- [Discord execute webhook](https://discord.com/developers/docs/resources/webhook#execute-webhook)

## Test

```powershell
python -m pytest
```

The tests mock platform behavior, so they do not publish anything externally.
