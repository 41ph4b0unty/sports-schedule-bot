"""Read-only preview: never calls Telegram or opens the daily state database."""
import sys
import argparse
import os
from pathlib import Path
import bot

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--v1', action='store_true', help='Use public V1 key 123 for this preview only')
    parser.add_argument('--listings-only', action='store_true', help='Preview TV and boxing without the football API')
    parser.add_argument('--output', type=Path, help='Optional preview destination')
    args = parser.parse_args()
    if args.v1:
        os.environ['THESPORTSDB_API_KEY'] = ''
        os.environ['THESPORTSDB_V1_FALLBACK'] = '1'
    try:
        if args.listings_only:
            from broadcasts import load_listings, boxing_section, uk_channels
            listings, notice = load_listings()
            lines = ['SOURCE LISTINGS PREVIEW — not matched to your football fixtures', notice]
            for row in listings:
                if row.get('strSport') == 'Soccer':
                    lines.append(f"{row.get('strEvent')} | {row.get('strTimeStamp')} UTC | UK TV: {', '.join(uk_channels([row])) or 'Not confirmed'}")
            message = '\n'.join(lines) + '\n\n' + boxing_section(listings, notice)
        else:
            message = bot.format_fixtures(bot.get_fixtures())
        destination = args.output or Path(__file__).with_name('schedule_preview.txt')
        destination.write_text(message, encoding='utf-8')
        print(f'Preview saved to {destination}. No Telegram messages sent.')
    except Exception as error:
        print('Preview failed (' + type(error).__name__ + '). No Telegram messages sent.')
        sys.exit(1)
