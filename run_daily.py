import logging
from contextlib import closing
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATE = ROOT / 'daily_posts.sqlite3'
UK = ZoneInfo('Europe/London')

def main():
    logging.basicConfig(filename=ROOT / 'daily_bot.log', level=logging.INFO,
                        format='%(asctime)s %(levelname)s %(message)s')
    day = datetime.now(UK).date().isoformat()
    try:
        import bot
        if not bot.TELEGRAM_TOKEN or not bot.TELEGRAM_CHANNEL_ID:
            raise RuntimeError('Missing Telegram configuration')
        with closing(sqlite3.connect(STATE, timeout=30)) as db, db:
            db.execute('CREATE TABLE IF NOT EXISTS posts (day TEXT PRIMARY KEY, status TEXT NOT NULL)')
            existing = db.execute('SELECT status FROM posts WHERE day = ?', (day,)).fetchone()
        if existing:
            logging.info('UK date %s already recorded: %s; skipping.', day, existing[0])
            print('Already recorded for today; no Telegram messages sent.')
            return 0 if existing[0] == 'sent' else 2
        # Fetch before claiming so a failed fixtures request can safely be retried.
        message = bot.format_fixtures(bot.get_fixtures())
        if not message or not message.strip():
            raise RuntimeError('Empty schedule')
        with closing(sqlite3.connect(STATE, timeout=30)) as db, db:
            claimed = db.execute('INSERT OR IGNORE INTO posts VALUES (?, ?)', (day, 'sending')).rowcount
        if not claimed:
            logging.info('Another process claimed UK date %s; skipping.', day)
            return 0
        # Commit the claim BEFORE any Telegram call. A crash/timeout blocks re-send.
        bot.send_schedule(bot.TELEGRAM_CHANNEL_ID, message)
        with closing(sqlite3.connect(STATE, timeout=30)) as db, db:
            db.execute('UPDATE posts SET status = ? WHERE day = ?', ('sent', day))
        logging.info('Schedule successfully sent for UK date %s.', day)
        print('Football schedule sent successfully.')
        return 0
    except Exception as error:
        # Exception messages may contain the token-bearing Telegram URL.
        logging.error('Run failed (%s). Check channel before retrying any sending record.', type(error).__name__)
        print('Run failed. See daily_bot.log; check Telegram before retrying.')
        return 1

if __name__ == '__main__':
    sys.exit(main())
