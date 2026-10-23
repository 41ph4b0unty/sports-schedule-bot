
from datetime import datetime
from zoneinfo import ZoneInfo
from broadcasts import football_tv

UK_TIME = ZoneInfo("Europe/London")


def format_fixtures(matches, listings=None):
    listings = listings or []
    """Format football fixtures into a readable Telegram message."""

    if not matches:
        return (
            "⚽ FOOTBALL SCHEDULE\n\n"
            "No fixtures were returned for the selected dates."
        )

    matches = sorted(
        matches,
        key=lambda match: match.get("utcDate", "")
    )

    lines = ["⚽ FOOTBALL SCHEDULE", ""]

    current_date = None

    for match in matches:
        utc_date = match.get("utcDate")

        if not utc_date:
            continue

        kickoff = datetime.fromisoformat(
            utc_date.replace("Z", "+00:00")
        ).astimezone(UK_TIME)

        fixture_date = kickoff.strftime("%A %d %B")

        if fixture_date != current_date:
            current_date = fixture_date
            lines.append(f"📅 {fixture_date}")

        competition = match.get("competition", {}).get(
            "name", "Football"
        )

        home = match.get("homeTeam", {}).get(
            "name", "Unknown team"
        )

        away = match.get("awayTeam", {}).get(
            "name", "Unknown team"
        )

        lines.append(
            f"🕒 {kickoff:%H:%M} — {competition}\n"
            f"   {home} vs {away}\n"
            f"📺 UK TV: {football_tv(match, listings)}"
        )

    lines.extend([
        "",
        "🇬🇧 All kick-off times are UK local time.",
        "TV listings may change. Not confirmed does not mean not televised."
    ])

    return "\n".join(lines)
