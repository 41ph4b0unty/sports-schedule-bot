"""Optional documented API only: no website scraping or inferred TV rights."""
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import requests

UK = ZoneInfo('Europe/London')
BASE = 'https://www.thesportsdb.com/api/v2/json'


def normal(value):
    return re.sub(r'\s+', ' ', str(value or '').casefold()).strip()


def timestamp(value):
    try:
        result = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result
    except (TypeError, ValueError):
        return None


def _load_v2(today=None):
    """Nine UTC dates cover today through day seven in UK time, including BST."""
    key = os.getenv('THESPORTSDB_API_KEY', '').strip()
    if not key:
        return [], 'TV source not connected; UK channels are Not confirmed.'
    today = today or datetime.now(UK).date()
    rows = []
    limited = False
    try:
        for offset in range(-1, 8):
            day = today + timedelta(days=offset)
            response = requests.get(
                f'{BASE}/filter/tv/day/{day.isoformat()}',
                headers={'X-API-KEY': key}, timeout=5)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or 'filter' not in payload:
                raise ValueError('Unexpected TV response')
            batch = payload['filter'] or []
            if not isinstance(batch, list) or any(not isinstance(r, dict) for r in batch):
                raise ValueError('Unexpected TV records')
            limited |= len(batch) >= 100
            for row in batch:
                start = timestamp(row.get('strTimeStamp'))
                if start and today <= start.astimezone(UK).date() <= today + timedelta(days=7):
                    rows.append(row)
    except (requests.RequestException, ValueError):
        # Never print exceptions: requests may contain private headers/URLs.
        logging.warning('TV API unavailable; using Not confirmed for missing listings.')
        return rows, 'TV source partly unavailable; missing UK channels are Not confirmed.'
    notice = 'TV listings: TheSportsDB (community maintained; coverage may be incomplete).'
    if limited:
        notice += ' Source result limit reached; some listings may be missing.'
    return rows, notice


def _records(payload, field):
    if not isinstance(payload, dict) or field not in payload:
        raise ValueError('Unexpected V1 response')
    rows = payload[field]
    if rows is None:
        return []
    if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
        raise ValueError('Unexpected V1 records')
    return rows


def load_v1(today=None):
    """Public key 123: intentionally limited data, no private key reuse."""
    today = today or datetime.now(UK).date()
    rows, boxing, fight_tv = [], [], []
    last_request = None
    def get(endpoint, params, field):
        nonlocal last_request
        if last_request is not None:
            time.sleep(max(0, 2.1 - (time.monotonic() - last_request)))
        last_request = time.monotonic()
        reply = requests.get('https://www.thesportsdb.com/api/v1/json/123/' + endpoint,
                             params=params, timeout=15)
        reply.raise_for_status()
        return _records(reply.json(), field)

    failed = False
    try:
        for offset in range(-1, 8):
            day = (today + timedelta(days=offset)).isoformat()
            rows.extend(get('eventstv.php', {'d': day, 's': 'Soccer',
                                            'a': 'United_Kingdom'}, 'tvevents'))
            # Boxing is league 4445 within Fighting, not sport=Boxing.
            boxing.extend(get('eventsday.php', {'d': day, 'l': '4445'}, 'events'))
            fight_tv.extend(get('eventstv.php', {'d': day, 's': 'Fighting',
                                                'a': 'United_Kingdom'}, 'tvevents'))
    except (requests.RequestException, ValueError) as error:
        logging.warning('V1 source unavailable (%s); keeping only previously retrieved records.',
                        type(error).__name__)
        failed = True

    for event in boxing:
        if str(event.get('idLeague')) != '4445' or not event.get('idEvent'):
            continue
        if normal(event.get('strStatus')) in ('cancelled', 'canceled', 'postponed'):
            continue
        start = event.get('strTimestamp')
        if not start and event.get('dateEvent'):
            start = event['dateEvent'] + 'T' + (event.get('strTime') or '00:00:00')
        base = dict(event, strSport='Boxing', strTimeStamp=start,
                    strCountry='', strChannel='',
                    _time_unconfirmed=not event.get('strTime') or event['strTime'].startswith('00:00'))
        # Event country is NOT channel country. Only matched TV records supply channels.
        rows.append(base)
        for listing in fight_tv:
            if (str(listing.get('idEvent')) == str(event['idEvent'])
                    and timestamp(listing.get('strTimeStamp')) == timestamp(start)):
                rows.append(dict(base, strCountry=listing.get('strCountry'),
                                 strChannel=listing.get('strChannel')))
    selected = []
    seen = set()
    for row in rows:
        start = timestamp(row.get('strTimeStamp'))
        if not start or not today <= start.astimezone(UK).date() <= today + timedelta(days=7):
            continue
        identity = (str(row.get('idEvent')), start, row.get('strCountry'), row.get('strChannel'))
        if identity not in seen:
            seen.add(identity)
            selected.append(row)
    notice = ('TheSportsDB free V1 sample: at most 1 TV listing per sport/date request '
              'and 3 boxing events per date; coverage is incomplete. '
              'Missing UK channels and PPV: Not confirmed.')
    if failed:
        notice += ' V1 request failed; results may be partial.'
    return selected, notice


def load_listings(today=None):
    enabled = normal(os.getenv('THESPORTSDB_V1_FALLBACK')) in ('1', 'true', 'yes')
    key = os.getenv('THESPORTSDB_API_KEY', '').strip()
    if not key:
        return load_v1(today) if enabled else _load_v2(today)
    rows, notice = _load_v2(today)
    if enabled and ('unavailable' in notice or not rows):
        fallback, extra = load_v1(today)
        return rows + fallback, notice + '\n' + extra
    return rows, notice


def uk_channels(rows):
    return sorted({r['strChannel'].strip() for r in rows
                   if normal(r.get('strCountry')) == 'united kingdom'
                   and isinstance(r.get('strChannel'), str) and r['strChannel'].strip()})


def football_tv(match, rows):
    start = timestamp(match.get('utcDate'))
    if not start:
        return 'Not confirmed'
    # Exact provider team names only. No fuzzy guesses, suffix removal or rights mapping.
    home = {normal(match.get('homeTeam', {}).get(field)) for field in ('name', 'shortName')}
    away = {normal(match.get('awayTeam', {}).get(field)) for field in ('name', 'shortName')}
    titles = {f'{h} vs {a}' for h in home if h for a in away if a}
    found = [r for r in rows if normal(r.get('strSport')) == 'soccer'
             and normal(r.get('strEvent')) in titles
             and timestamp(r.get('strTimeStamp')) == start]
    # Multiple provider event IDs for this title/time are ambiguous.
    ids = {r.get('idEvent') for r in found}
    if len(ids) != 1 or not next(iter(ids), None):
        return 'Not confirmed'
    return ', '.join(uk_channels(found)) or 'Not confirmed'


def boxing_section(rows, notice):
    groups = {}
    for row in rows:
        if normal(row.get('strSport')) != 'boxing' or not row.get('idEvent') or not row.get('strEvent'):
            continue
        start = timestamp(row.get('strTimeStamp'))
        if start:
            groups.setdefault((str(row['idEvent']), start), []).append(row)
    lines = ['🥊 BOXING — NEXT 8 UK DATES']
    for (_, start), event_rows in sorted(groups.items(), key=lambda item: item[0][1]):
        channels = uk_channels(event_rows)
        tv = ', '.join(channels) or 'Not confirmed'
        # DAZN, Sky, etc. alone do not prove PPV or subscription inclusion.
        ppv = 'Listed as PPV / Box Office' if any(
            re.search(r'\bppv\b|\bbox office\b|pay.per.view', c, re.I) for c in channels
        ) else 'Not confirmed'
        when = (f"📅 {event_rows[0].get('dateEvent', '')} — source date; UK start time Not confirmed"
                if event_rows[0].get('_time_unconfirmed') else
                f'📅 {start.astimezone(UK):%a %d %b %H:%M} UK — listed event time')
        lines.extend([when,
                      str(event_rows[0]['strEvent']), f'📺 UK TV: {tv}', f'PPV: {ppv}'])
    if not groups:
        lines.append('No boxing listings available from the connected source. This does not mean no fights are scheduled.')
    lines.extend(['Ring-walk times and PPV prices: Not confirmed.',
                  'Source-listed events only; this is not a complete boxing calendar.', notice])
    return '\n'.join(lines)
