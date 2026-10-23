# Sports Schedule Telegram Bot

A Python bot that builds a football schedule, enriches it with available UK television listings, and includes a separate boxing section. Designed for unattended daily execution on Windows with UK local dates and conservative duplicate-send protection.

This project demonstrates API integration, timezone-aware formatting, optional data-source fallback, durable SQLite state, background scheduling, and offline testing. TV coverage is deliberately presented as incomplete when the source cannot confirm it.

## Features

- Retrieves football fixtures from football-data.org for today through seven days ahead (eight UK calendar dates).
- Converts kickoff times using `Europe/London`, including GMT/BST changes.
- Matches UK TV channels using exact team names or supplied short names, exact kickoff and an unambiguous event ID. It never infers a broadcaster from league rights.
- Supports TheSportsDB V2 and an optional, rate-paced free V1 fallback.
- Uses V1 Boxing league `4445` within Fighting to keep MMA out of the boxing section. Unknown source midnight times remain unconfirmed.
- Splits long Telegram messages at line boundaries and checks Telegram responses.
- Claims the UK date in SQLite before sending, blocking overlapping or uncertain repeat sends.
- Provides read-only previews and offline tests without requiring real credentials.

## Project structure

| File | Purpose |
| --- | --- |
| `bot.py` | Football API, combined message composition and Telegram transport |
| `config.py` | Loads private settings from the adjacent `.env` |
| `formatter.py` | Football formatting in UK local time |
| `broadcasts.py` | Optional TV sources, strict matching and boxing formatting |
| `run_daily.py` | Daily SQLite claim, duplicate protection and safe error logging |
| `preview_schedule.py` | Preview without Telegram sends or daily-state changes |
| `tests/test_bot.py` | Offline regression tests with synthetic credentials and mocked network calls |

## Requirements

- Python 3.10 or newer is required by the syntax. Validation was performed with Python 3.15 on Windows; other versions have not been tested here.
- A football-data.org token with access to the requested competitions.
- A Telegram bot token and a target chat/channel ID for actual posting. The bot must have permission to post there.
- Optional: a V2-capable TheSportsDB key or opt-in public V1 fallback.

The dependency file pins the direct packages installed during validation. It is not a complete transitive dependency lock file.

## Install on Windows

From a terminal in your own project folder:

```powershell
py -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Only copy the example for a new checkout. If `.env` already exists, keep it and edit it privately instead of overwriting it.

| Setting | Meaning |
| --- | --- |
| `TELEGRAM_TOKEN` | Private Telegram bot token |
| `TELEGRAM_CHANNEL_ID` | Destination chat/channel ID; keep your real value private |
| `FOOTBALL_DATA_TOKEN` | Private football-data.org token |
| `THESPORTSDB_API_KEY` | Optional premium V2 key |
| `THESPORTSDB_V1_FALLBACK` | `1` enables the limited free V1 fallback; default `0` |

The V1 fallback uses public key `123` internally. Do not put `123` into the premium V2 setting. V2 remains first choice when configured and successful. With the fallback enabled, V1 is used when V2 is unconfigured, fails, or returns no rows; it does not fill every individual gap in an otherwise successful V2 response.

## Preview before posting

Preview only the free V1 source listings, without using your football token:

```powershell
& '.\.venv\Scripts\python.exe' '.\preview_schedule.py' --v1 --listings-only
notepad '.\schedule_preview.txt'
```

Preview the complete message against your football fixtures using free V1:

```powershell
& '.\.venv\Scripts\python.exe' '.\preview_schedule.py' --v1
notepad '.\schedule_preview.txt'
```

Preview with your configured source choices:

```powershell
& '.\.venv\Scripts\python.exe' '.\preview_schedule.py'
```

These commands make read-only API requests and write a local preview. They do not send Telegram messages or open the duplicate-state database. `--v1` changes source selection only for that process; it does not edit `.env`. Listings-only output is raw source coverage, not confirmation that a listing matches one of your selected football fixtures.

V1 can take one to two minutes. It makes at most 27 requests per run, spaced at least 2.1 seconds apart. Avoid simultaneous previews. Requests stop after an API/network/schema failure and results are labelled partial.

## Offline tests

```powershell
& '.\.venv\Scripts\python.exe' -B -m unittest discover -s tests -v
```

Tests use synthetic credentials, mocked HTTP requests and temporary databases. They do not load your `.env`, send Telegram messages, or touch your real daily database. Coverage includes exact fixture matching, foreign-channel exclusion, GMT/BST changes, missing keys, malformed source responses, source selection, strict boxing identity/time matching, uncertain start times and PPV, and duplicate blocking after successful or uncertain sends.

## Daily posting on Windows

**The following command sends to the Telegram destination configured in `.env`.** Use the preview commands for testing.

```powershell
& '.\.venv\Scripts\python.exe' '.\run_daily.py'
```

For a new installation, configure Windows Task Scheduler with:

| Field | Value |
| --- | --- |
| Trigger | Daily at 08:00, with Windows configured for UK local time |
| Program | Absolute path to the checkout's `.venv\Scripts\python.exe` |
| Arguments | Absolute path to `run_daily.py`, quoted if it contains spaces |
| Start in | Absolute path to the checkout folder |

The existing deployment uses a task named **Sports Bot - Daily 0800 UK**. Preparing this repository does not modify that task. No terminal needs to stay open. Windows must be able to run the task and reach the internet; wake/catch-up and signed-out behavior depend on the task settings. The Python code independently uses UK dates, but a Windows trigger in another system timezone is not automatically an 08:00 UK trigger.

Runtime files are created beside the scripts: `daily_posts.sqlite3` stores daily state and `daily_bot.log` records outcomes. Keep the database across upgrades. Fetching/composition happens before the date is claimed; sending happens after the claim is committed. A timeout, crash or partial multi-message send can leave the day marked `sending`. Check the destination before any manual recovery; automatic retries are deliberately blocked to avoid duplicates. This favors avoiding repeated posts over guaranteeing delivery.

Exit codes: `0` for success or an already-sent day, `2` when an existing uncertain claim blocks retry, and `1` for a failed run. A concurrent process that loses the claim also exits `0` without sending.

## Coverage and limitations

- Football requests the configured competition codes in `bot.py`. Provider plan permissions may exclude some competitions or reject the request.
- TheSportsDB is community maintained. Listings can be absent, stale, or incorrect. A returned record is not an official broadcaster guarantee.
- The documented free V1 limits are one TV record per sport/date request and three schedule events per date request. Per-event TV lookup is limited to two records; the current fallback uses date-based listings instead. It does not circumvent free limits.
- V2 daily TV responses can also be capped; the message warns when the known result limit is reached.
- Strict matching intentionally leaves differing team names or times unconfirmed. **Not confirmed does not mean not televised.**
- V1 boxing schedule records are filtered to league `4445`. Generic V2 Fighting TV rows without explicit boxing identity are not treated as boxing. Complete boxing coverage is not promised.
- Ring-walk times, PPV prices and subscription inclusion are not inferred. PPV is only identified when the UK channel name explicitly says PPV or Box Office.
- The bot uses documented API endpoints rather than scraping broadcaster websites. Check each provider's current terms and access requirements for your intended use.

## Secrets and publication hygiene

Commit only source, documentation, the empty `.env.example` and offline tests. `.gitignore` excludes private configuration, databases, logs, previews, backups, virtual environments and local editor/development files. It does not remove files already tracked or secrets already in Git history.

Before a future publication, inspect `git status --short`, `git ls-files` and the staged diff. If a real credential is ever committed, treat it as exposed: rotate it with its provider and clean the history before publication. This repository preparation does not rotate credentials, create a remote, commit changes or publish anything.

## Data sources

- [football-data.org documentation](https://www.football-data.org/documentation/quickstart)
- [TheSportsDB API documentation](https://api.thesportsdb.com/documentation)
- [Telegram Bot API](https://core.telegram.org/bots/api)
