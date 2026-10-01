from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from bank_ui_scope import resolve_scope
from serve_fintrace_scoped import handler_for, scoped_app, replace_once
from bank_retrieval import ROOT


class ScopeTests(unittest.TestCase):
    def test_all_defaults_do_not_rewrite_question(self):
        result = resolve_scope('What was profit?')
        self.assertEqual(result['effective_question'], 'What was profit?')
        self.assertEqual(result['summary'], 'CBA and NAB / FY2024 and FY2025')

    def test_filters_fill_both_missing_fields(self):
        result = resolve_scope('profit?', {'company': 'CBA', 'year': '2025'})
        self.assertEqual(result['effective_question'], 'profit?\nFor CBA, FY2025.')

    def test_explicit_question_wins_both_conflicts(self):
        result = resolve_scope('NAB profit FY2024?', {'company': 'CBA', 'year': '2025'})
        self.assertEqual(result['effective_question'], 'NAB profit FY2024?')
        self.assertEqual(result['effective'], {'company': 'NAB', 'year': '2024'})
        self.assertEqual(len(result['notes']), 2)

    def test_only_missing_year_is_added(self):
        result = resolve_scope('NAB profit?', {'company': 'CBA', 'year': '2024'})
        self.assertEqual(result['effective_question'], 'NAB profit?\nFor FY2024.')

    def test_only_missing_company_is_added(self):
        result = resolve_scope('profit FY24?', {'company': 'NAB', 'year': '2025'})
        self.assertEqual(result['effective_question'], 'profit FY24?\nFor NAB.')
        self.assertEqual(result['effective']['year'], '2024')

    def test_full_names(self):
        for name, expected in [('Commonwealth Bank of Australia', 'CBA'), ('National Australia Bank', 'NAB')]:
            with self.subTest(name=name):
                self.assertEqual(resolve_scope(name + ' profit FY2025')['effective']['company'], expected)

    def test_explicit_both_banks_and_years(self):
        q = 'Compare CBA and NAB in 2024 and 2025'
        result = resolve_scope(q, {'company': 'CBA', 'year': '2025'})
        self.assertEqual(result['effective_question'], q)
        self.assertEqual(result['effective'], {'company': 'all', 'year': 'all'})

    def test_all_words_override_filters(self):
        for q in ['profit for both banks in both years', 'profit for all companies in all available years']:
            with self.subTest(q=q):
                result = resolve_scope(q, {'company': 'CBA', 'year': '2025'})
                self.assertEqual(result['effective_question'], q)
                self.assertEqual(result['effective'], {'company': 'all', 'year': 'all'})

    def test_unsupported_bank_not_replaced(self):
        result = resolve_scope('Westpac profit 2025', {'company': 'CBA'})
        self.assertEqual(result['effective_question'], 'Westpac profit 2025')
        self.assertNotIn('CBA', result['summary'])

    def test_unsupported_year_not_replaced(self):
        for q in ['NAB profit 2026', 'NAB profit FY26', 'NAB profit 2023']:
            with self.subTest(q=q):
                result = resolve_scope(q, {'year': '2025'})
                self.assertEqual(result['effective_question'], q)
                self.assertEqual(result['effective']['year'], 'all')

    def test_relative_period_not_silently_converted(self):
        for q in ['CBA profit last year', 'CBA current profit', 'CBA profit next year']:
            with self.subTest(q=q):
                self.assertEqual(resolve_scope(q, {'year': '2024'})['effective_question'], q)

    def test_preserves_original_restated_periods(self):
        q = 'CBA FY2024 original statutory profit versus the FY2025 restated comparative'
        self.assertEqual(resolve_scope(q, {'year': '2025'})['effective_question'], q)

    def test_bad_scope_rejected(self):
        for scope in [[], 'CBA', {'company': 'Westpac'}, {'year': 2025}, {'year': '2026'}, {'extra': True}, {'company': {}}]:
            with self.subTest(scope=scope), self.assertRaises(ValueError):
                resolve_scope('profit', scope)

    def test_question_limits(self):
        for q in [None, [], '', '  ', 'x' * 2001]:
            with self.subTest(q=str(q)[:20]), self.assertRaises(ValueError):
                resolve_scope(q)
        self.assertEqual(len(resolve_scope('x' * 2000)['effective_question']), 2000)
        with self.assertRaisesRegex(ValueError, 'shorten'):
            resolve_scope('x' * 2000, {'company': 'CBA', 'year': '2025'})

    def test_mixed_request_shares_selected_context(self):
        from answer_bank_simplified import split_mixed
        q = resolve_scope('What was profit and why did it increase?', {'company': 'CBA', 'year': '2025'})['effective_question']
        numeric, narrative = split_mixed(q)
        for branch in [numeric, narrative]:
            self.assertIn('CBA', branch)
            self.assertIn('FY2025', branch)

    def test_commbank_alias_retains_canonical_context(self):
        result = resolve_scope('CommBank profit FY2025', {'company': 'NAB'})
        self.assertEqual(result['effective']['company'], 'CBA')
        self.assertIn('For CBA.', result['effective_question'])

    def test_overlay_is_fail_closed(self):
        with self.assertRaises(ValueError):
            replace_once('xx', 'x', 'y')
        with self.assertRaises(ValueError):
            scoped_app('different app')

    def test_overlay_history_scope_and_payload(self):
        app = scoped_app((ROOT/'web/app.mjs').read_text(encoding='utf-8'))
        for expected in ['JSON.stringify({ question, scope })', 'restoreScope(entry.scope)',
                         'disableScope(state.busy)', 'renderScope(result, fragment)', 'scope: effectiveScope']:
            self.assertIn(expected, app)


class Stub:
    version = 'scope-test'
    def answer(self, question):
        return {'question': question, 'received_question': question, 'version': self.version,
                'answer': {'status': 'source_bound_answer', 'message': 'Test answer.'}}


class ScopeServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Stub()))
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def post(self, payload, headers=None):
        req = Request(self.url + '/ask', data=json.dumps(payload).encode(),
                      headers={'Content-Type': 'application/json', **(headers or {})})
        with urlopen(req) as response:
            return json.load(response)

    def test_scoped_roundtrip_and_exports(self):
        result = self.post({'question': 'profit?', 'scope': {'company': 'CBA', 'year': '2025'}})
        self.assertEqual(result['question'], 'profit?')
        self.assertEqual(result['received_question'], 'profit?\nFor CBA, FY2025.')
        self.assertIn('CBA / FY2025', result['display_text'])
        self.assertEqual(result['ui_scope']['selected']['company'], 'CBA')

    def test_old_payload_remains_valid(self):
        self.assertEqual(self.post({'question': 'CBA profit FY2025'})['received_question'], 'CBA profit FY2025')

    def test_conflict_note_in_copy(self):
        result = self.post({'question': 'NAB profit FY2024', 'scope': {'company': 'CBA', 'year': '2025'}})
        self.assertIn('takes precedence', result['display_text'])
        self.assertEqual(result['received_question'], 'NAB profit FY2024')

    def test_invalid_scope_does_not_call_backend(self):
        with self.assertRaises(HTTPError) as error:
            self.post({'question': 'profit', 'scope': {'company': 'BHP'}})
        self.assertEqual(error.exception.code, 400)

    def test_same_origin_is_enforced(self):
        with self.assertRaises(HTTPError) as error:
            self.post({'question': 'profit'}, {'Origin': 'http://localhost:9999'})
        self.assertEqual(error.exception.code, 403)

    def test_host_is_enforced(self):
        with self.assertRaises(HTTPError) as error:
            self.post({'question': 'profit'}, {'Host': 'example.com'})
        self.assertEqual(error.exception.code, 403)

    def test_controls_and_modules_served(self):
        with urlopen(self.url + '/') as response:
            html = response.read().decode()
            self.assertIn("script-src 'self'", response.headers['Content-Security-Policy'])
        self.assertEqual(html.count('id="company-filter"'), 1)
        self.assertEqual(html.count('id="year-filter"'), 1)
        self.assertIn('without generative AI', html)
        for path, expected in [('/app.mjs', 'JSON.stringify({ question, scope })'),
                               ('/scope-controls.mjs', 'export function restoreScope'),
                               ('/scope.css', '@media(max-width:480px)')]:
            with urlopen(self.url + path) as response:
                self.assertIn(expected, response.read().decode())


if __name__ == '__main__':
    unittest.main()
