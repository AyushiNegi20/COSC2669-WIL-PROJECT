from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
import unittest
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from serve_fintrace_v12 import handler_for


class Stub:
    version = 'v12-test'

    def answer(self, question):
        return {'question': question, 'version': self.version, 'answer': {
            'status': 'source_bound_answer', 'message': 'Cash profit and statutory profit are shown separately.'}}


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Stub()))
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()

    def test_health_identifies_current_candidate(self):
        with urlopen(self.url+'/health') as response: result = json.load(response)
        self.assertEqual(result['version'], 'v12-test')
        self.assertEqual(result['ambiguity_policy'], 'labelled supported alternatives')

    def test_ui_and_api_are_connected(self):
        with urlopen(self.url+'/') as response:
            self.assertIn(b'Qwen', response.read())
        request = Request(self.url+'/ask', data=json.dumps({'question': 'CBA profit FY2025?'}).encode(),
                          headers={'Content-Type': 'application/json'})
        with urlopen(request) as response: result = json.load(response)
        self.assertEqual(result['version'], 'v12-test')
        self.assertIn('Cash profit and statutory profit', result['display_text'])


if __name__ == '__main__': unittest.main()
