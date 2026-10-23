import os
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch
import sys
import types
from contextlib import closing

# Tests never load real credentials or contact Telegram.
sys.modules['config'] = types.SimpleNamespace(TELEGRAM_TOKEN='test',
    FOOTBALL_DATA_TOKEN='test', TELEGRAM_CHANNEL_ID='test')
import broadcasts as tv
import formatter
import bot
import run_daily

MATCH = {'utcDate': '2026-10-24T14:00:00Z',
         'homeTeam': {'name': 'Arsenal FC', 'shortName': 'Arsenal'},
         'awayTeam': {'name': 'Chelsea FC', 'shortName': 'Chelsea'}}
ROW = dict(idEvent='1', strSport='Soccer', strEvent='Arsenal vs Chelsea',
           strTimeStamp='2026-10-24 14:00:00', strCountry='United Kingdom',
           strChannel='Example UK channel')


class OfflineCase(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch('requests.get', side_effect=AssertionError('Unmocked HTTP GET forbidden')))
        self.enterContext(patch('requests.post', side_effect=AssertionError('HTTP POST forbidden')))


class FootballStage(OfflineCase):
    def test_exact_match_and_reject_wrong_region_time_team_sport(self):
        self.assertEqual(tv.football_tv(MATCH, [ROW]), 'Example UK channel')
        for field, value in [('strCountry', 'United States'),
                             ('strTimeStamp', '2026-10-24 13:00:00'),
                             ('strEvent', 'Arsenal Women vs Chelsea Women'),
                             ('strSport', 'Boxing')]:
            self.assertEqual(tv.football_tv(MATCH, [dict(ROW, **{field: value})]), 'Not confirmed')
        self.assertEqual(tv.football_tv(MATCH, [ROW, dict(ROW, idEvent='2')]), 'Not confirmed')

    def test_missing_key_no_network(self):
        with patch.dict(os.environ, {'THESPORTSDB_API_KEY': ''}), patch('requests.get') as get:
            self.assertIn('not connected', tv.load_listings()[1])
            get.assert_not_called()

    def test_api_schema_dates_cap_and_failure(self):
        reply = Mock()
        reply.json.return_value = {'filter': [ROW] * 100}
        with patch.dict(os.environ, {'THESPORTSDB_API_KEY': 'test'}), patch('requests.get', return_value=reply) as get:
            rows, notice = tv.load_listings(date(2026, 10, 24))
            self.assertEqual(get.call_count, 9)
            self.assertIn('limit reached', notice)
            self.assertTrue(rows)
            reply.json.return_value = {'error': 'denied'}
            self.assertIn('unavailable', tv.load_listings(date(2026, 10, 24))[1])

    def test_uk_clock_change(self):
        for utc, local in [('2026-10-24T14:00:00Z', '15:00'), ('2026-10-25T14:00:00Z', '14:00')]:
            self.assertIn(local, formatter.format_fixtures([dict(MATCH, utcDate=utc)]))


class BoxingStage(OfflineCase):
    def test_ppv_not_inferred_from_dazn(self):
        row = dict(ROW, strSport='Boxing', strEvent='Fighter A vs Fighter B', strChannel='DAZN')
        message = tv.boxing_section([row, row], 'Source')
        self.assertEqual(message.count('Fighter A vs Fighter B'), 1)
        self.assertIn('PPV: Not confirmed', message)
        self.assertIn('Listed as PPV', tv.boxing_section([dict(row, strChannel='Example Box Office')], 'Source'))
        self.assertIn('UK TV: Not confirmed', tv.boxing_section([dict(row, strCountry='United States')], 'Source'))

    def test_combined_runner_duplicate_and_uncertain_send(self):
        with tempfile.TemporaryDirectory() as folder:
            for status in ('sent', 'sending'):
                state = Path(folder) / (status + '.sqlite3')
                with patch.object(run_daily, 'STATE', state), patch('logging.basicConfig'), patch.object(bot, 'get_fixtures', return_value=[MATCH]), patch.object(bot, 'load_listings', return_value=([], 'Not connected')), patch.object(bot, 'send_schedule') as send:
                    if status == 'sending':
                        send.side_effect = TimeoutError()
                    self.assertEqual(run_daily.main(), 0 if status == 'sent' else 1)
                    self.assertEqual(run_daily.main(), 0 if status == 'sent' else 2)
                    self.assertEqual(send.call_count, 1)
                    message = send.call_args.args[1]
                    self.assertIn('UK TV: Not confirmed', message)
                    self.assertIn('BOXING', message)
                    with closing(sqlite3.connect(state)) as db:
                        self.assertEqual(db.execute('SELECT status FROM posts').fetchone()[0], status)


class V1Fallback(OfflineCase):
    def test_free_data_normalization_region_and_no_midnight_guess(self):
        event = dict(idEvent='box1', idLeague='4445', strSport='Fighting',
                     strEvent='Boxer A vs Boxer B', dateEvent='2026-10-24',
                     strTime='00:00:00', strTimestamp='2026-10-24T00:00:00',
                     strCountry='United Kingdom', strChannel='NOT A TV RECORD')
        calls = []
        def get(url, params, **kwargs):
            calls.append((url, params))
            reply = Mock()
            if url.endswith('eventsday.php'):
                reply.json.return_value = {'events': [event, dict(event, idEvent='mma', idLeague='4443')]}
            elif params['s'] == 'Soccer':
                reply.json.return_value = {'tvevents': [ROW]}
            else:
                reply.json.return_value = {'tvevents': [dict(ROW, idEvent='mma', strSport='Fighting')]}
            return reply
        with patch('requests.get', side_effect=get), patch('time.sleep'):
            rows, notice = tv.load_v1(date(2026, 10, 24))
        self.assertEqual(len(calls), 27)
        self.assertTrue(all('/123/' in url for url, _ in calls))
        self.assertIn('incomplete', notice)
        message = tv.boxing_section(rows, notice)
        self.assertIn('UK start time Not confirmed', message)
        self.assertIn('UK TV: Not confirmed', message)
        self.assertNotIn('NOT A TV RECORD', message)
        self.assertNotIn('mma', message)
        self.assertEqual(message.count('Boxer A vs Boxer B'), 1)
        self.assertEqual(tv.football_tv(MATCH, rows), 'Example UK channel')

    def test_selection_opt_in_v2_priority_and_failure(self):
        with patch.dict(os.environ, {'THESPORTSDB_API_KEY': '', 'THESPORTSDB_V1_FALLBACK': ''}), patch.object(tv, 'load_v1') as v1:
            tv.load_listings()
            v1.assert_not_called()
        with patch.dict(os.environ, {'THESPORTSDB_API_KEY': 'private', 'THESPORTSDB_V1_FALLBACK': '1'}), patch.object(tv, '_load_v2', return_value=([ROW], 'OK')), patch.object(tv, 'load_v1', return_value=([], 'V1')) as v1:
            self.assertEqual(tv.load_listings(), ([ROW], 'OK'))
            v1.assert_not_called()
            with patch.object(tv, '_load_v2', return_value=([], 'unavailable')):
                self.assertIn('V1', tv.load_listings()[1])
                v1.assert_called_once()

    def test_malformed_and_null_responses(self):
        self.assertEqual(tv._records({'events': None}, 'events'), [])
        for payload in ({'error':'denied'}, {'events':'wrong'}, {'events':[None]}):
            with self.assertRaises(ValueError):
                tv._records(payload, 'events')
        with patch('requests.get', side_effect=tv.requests.Timeout()), patch('time.sleep'):
            rows, notice = tv.load_v1(date(2026, 10, 24))
        self.assertEqual(rows, [])
        self.assertIn('failed', notice)

    def test_boxing_tv_requires_matching_id_and_time(self):
        event = dict(idEvent='b1', idLeague='4445', strEvent='A vs B',
                     dateEvent='2026-10-24', strTime='20:00:00',
                     strTimestamp='2026-10-24T20:00:00')
        listings = [dict(ROW, idEvent='b1', strTimeStamp='2026-10-24 20:00:00', strChannel='DAZN UK'),
                    dict(ROW, idEvent='b1', strTimeStamp='2026-10-24 20:00:00', strCountry='United States', strChannel='Foreign PPV'),
                    dict(ROW, idEvent='wrong', strTimeStamp='2026-10-24 20:00:00', strChannel='Wrong Box Office'),
                    dict(ROW, idEvent='b1', strTimeStamp='2026-10-24 21:00:00', strChannel='Wrong time PPV')]
        def get(url, params, **kwargs):
            reply = Mock()
            reply.json.return_value = ({'events': [event]} if url.endswith('eventsday.php') else
                                      {'tvevents': listings if params['s'] == 'Fighting' else None})
            return reply
        with patch('requests.get', side_effect=get), patch('time.sleep'):
            rows, notice = tv.load_v1(date(2026, 10, 24))
        message = tv.boxing_section(rows, notice)
        self.assertIn('UK TV: DAZN UK', message)
        self.assertIn('PPV: Not confirmed', message)
        self.assertNotIn('Foreign PPV', message)
        self.assertNotIn('Wrong', message)


if __name__ == '__main__':
    unittest.main()
