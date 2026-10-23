
import requests
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import TELEGRAM_TOKEN, FOOTBALL_DATA_TOKEN, TELEGRAM_CHANNEL_ID
from formatter import format_fixtures as format_football
from broadcasts import load_listings, boxing_section

TELEGRAM_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
FOOTBALL_URL = "https://api.football-data.org/v4/matches"

COMPETITIONS = "PL,PD,BL1,SA,FL1,CL,EL,FAC"


def format_fixtures(matches):
    # The existing guarded daily runner calls this once before claiming the day.
    listings, notice = load_listings()
    return format_football(matches, listings) + "\n" + notice + "\n\n" + boxing_section(listings, notice)


def get_fixtures():
    if not FOOTBALL_DATA_TOKEN:
        raise RuntimeError("Football API token is missing.")

    today = datetime.now(ZoneInfo("Europe/London")).date()

    response = requests.get(
        FOOTBALL_URL,
        headers={"X-Auth-Token": FOOTBALL_DATA_TOKEN.strip()},
        params={
            "dateFrom": today.isoformat(),
            "dateTo": (today + timedelta(days=7)).isoformat(),
            "competitions": COMPETITIONS,
        },
        timeout=20,
    )
    response.raise_for_status()

    return response.json().get("matches", [])


def send_schedule(chat_id, message):
    # Split long messages at line boundaries.
    # Keep each message comfortably below Telegram's limit.
    max_length = 4000
    chunks = []
    current_chunk = ""

    for line in message.splitlines():
        # Handle an unusually long individual line safely.
        while len(line) > max_length:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
                current_chunk = ""

            chunks.append(line[:max_length])
            line = line[max_length:]

        candidate = f"{current_chunk}\n{line}" if current_chunk else line

        if len(candidate) > max_length:
            chunks.append(current_chunk.rstrip())
            current_chunk = line
        else:
            current_chunk = candidate

    if current_chunk:
        chunks.append(current_chunk.rstrip())

    for chunk in chunks:
        response = requests.post(
            f"{TELEGRAM_URL}/sendMessage",
            json={"chat_id": chat_id, "text": chunk},
            timeout=15,
        )
        response.raise_for_status()
        if not response.json().get('ok'):
            raise RuntimeError('Telegram rejected the message')


def main():
    if not TELEGRAM_TOKEN:
        print("Telegram token is missing. Check your .env file.")
        return

    chat_id = TELEGRAM_CHANNEL_ID
    if not chat_id:
        print("Telegram channel ID is missing. Check your .env file.")
        return

    try:
        print("Fetching football fixtures...")
        matches = get_fixtures()

        message = format_fixtures(matches)
        send_schedule(chat_id, message)

        print("Success! Football schedule sent to Telegram.")

    except (requests.RequestException, RuntimeError) as error:
        print("Could not send the football schedule.")
        print("Error type:", type(error).__name__)


if __name__ == "__main__":
    from run_daily import main as daily_main
    raise SystemExit(daily_main())
