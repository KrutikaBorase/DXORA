# Automated Multi-Platform Posting API

A small FastAPI service that publishes one short update to five platforms:

- Mastodon
- Bluesky
- DEV Community
- Telegram
- Discord

The optional Gemini integration provides feedback on the message. It does not
publish content, and it is reported separately from the posting results.

Each platform is configured with environment variables. Platforms are attempted
concurrently, and one failure does not stop the others. Results remain in the
configured platform order. HTTP requests have a 20-second timeout per operation.

## Requirements

- Python 3.10 or newer
- API credentials for the platforms you want to use

## Run locally

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env and add credentials for one or more platforms.
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
# Edit .env and add credentials for one or more platforms.
uvicorn app.main:app --host 0.0.0.0 --port 4000
```

The API has no authentication. Bind to `127.0.0.1` instead of `0.0.0.0` on
untrusted networks.

Interactive API documentation is available at
<http://localhost:4000/docs>.

## Request

`POST /posting` accepts one message with exactly one HTTP or HTTPS link. The
message, including the link, must be no longer than 200 characters. Other
links, including bare domains, are rejected. Bluesky posts include a rich-text
facet so the CTA is clickable.

```powershell
Invoke-RestMethod `
  -Uri http://localhost:4000/posting `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"message":"Check out our latest business platform: https://example.com"}'
```

```bash
curl -X POST http://localhost:4000/posting \
  -H 'Content-Type: application/json' \
  -d '{"message":"Check out our latest business platform: https://example.com"}'
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
      "platform": "DEV Community",
      "status": "failed",
      "posted_url": null,
      "public_access": false,
      "date": null,
      "time": null,
      "error": "DEVTO_API_KEY is not configured"
    }
  ],
  "gemini": {
    "status": "not_configured",
    "feedback": null,
    "error": "GEMINI_API_KEY is not configured"
  }
}
```

`success` is true when at least one platform accepts the post. A successful
Telegram post can have no public URL because Telegram private chats do not
provide one. Times are UTC.

When `GEMINI_API_KEY` is set, the original message is also sent to Google's
Gemini API for brief feedback, concurrently with posting. Gemini's feedback
does not change the message or the overall posting success flag. A Gemini
failure is reported separately and does not stop posting. This may incur API
charges; do not enable it for messages you cannot send to Google. Gemini
generates text and does not provide a public post URL.

`public_access` is conservative: `false` also means public access could not be
confirmed. Mastodon uses the returned status visibility; Telegram public channels
and supergroups with a username get a `t.me` link. Bluesky and DEV Community
are checked through their unauthenticated public APIs; a failed check does not
change a successful publication into a failure. Discord webhook responses do
not establish channel permissions, so Discord is reported as `false`.

## Proof of working

On 17 November 2026, a live request using `Posting API demo:
https://example.com` returned success for all five platforms. The DEV and
Mastodon posts were reachable without signing in; the Bluesky post and its
link facet were checked through the public API. The log predates the concurrent
posting, automatic public checks, and optional Gemini integration.

- [Swagger UI request screenshot](docs/proof/swagger-request.png)
- [Sanitized results log](docs/proof/latest-posting-results.txt)
- [Mastodon post](https://mastodon.social/@krutika_01/117632053988717752)
- [Bluesky post](https://bsky.app/profile/kr-ut.bsky.social/post/3n2j62ywzxf2n)
- [DEV Community article](https://dev.to/krutika_borse_864ff6bfe5e/posting-api-demo-46o4)
- [Discord message](https://discord.com/channels/1571947972432896030/1571947972998987938/1572244508542771353)

The Telegram message was sent to a private destination, so no public post URL
was returned. Discord access depends on channel permissions.

## Platform setup

Copy `.env.example` to `.env`. Only set credentials for platforms you intend
to use. Do not commit `.env` or access tokens.

For DEV Community, generate an API key in Settings > Extensions > DEV Community
API Keys and set `DEVTO_API_KEY` in `.env`. Each message is published as an
article, with a title derived from the text and the full message as its body.
Follow DEV Community's rules, especially when posting promotional content.

To enable Gemini feedback, create an API key in
[Google AI Studio](https://aistudio.google.com/apikey) and set `GEMINI_API_KEY`
in `.env`. The integration uses `gemini-3.5-flash-lite`; without a key, Gemini
is reported as `not_configured`.

Official API references:

- [Mastodon REST API](https://docs.joinmastodon.org/methods/statuses/)
- [Bluesky create session](https://docs.bsky.app/docs/api/com-atproto-server-create-session)
- [Bluesky create record](https://docs.bsky.app/docs/api/com-atproto-repo-create-record)
- [Bluesky links and rich text](https://bsky.network/docs/about-bluesky-content/post-richtext/)
- [DEV Community article API](https://developers.forem.com/api/v1#tag/articles/operation/createArticle)
- [Telegram Bot API sendMessage](https://core.telegram.org/bots/api#sendmessage)
- [Discord execute webhook](https://discord.com/developers/docs/resources/webhook#execute-webhook)
- [Gemini generateContent API](https://ai.google.dev/api/generate-content)

## Test

```powershell
python -m pytest
```

The tests mock platform behavior, so they do not publish anything externally.
