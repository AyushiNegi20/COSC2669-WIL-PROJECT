from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from threading import Thread
import unittest
from urllib.request import Request, urlopen
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from serve_fintrace_simplified import handler_for


class Stub:
    version = 'simplified-candidate-1'
    def answer(self, question):
        return {'question': question, 'version': self.version, 'route': 'numeric',
                'generation': {'status': 'skipped'},
                'answer': {'status': 'source_bound_answer', 'message': 'Source-backed numbers.'}}


class SimplifiedServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(Stub()))
        cls.thread = Thread(target=cls.server.serve_forever, daemon=True); cls.thread.start()
        cls.url = 'http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
    def test_ui_discloses_new_routing(self):
        with urlopen(self.url+'/') as response: html = response.read().decode()
        self.assertIn('without generative AI', html); self.assertIn('Definitions and explanations use local Qwen', html)
        self.assertNotIn('Be specific about', html)
    def test_api_keeps_source_template_route(self):
        with urlopen(self.url+'/health') as response: self.assertEqual(json.load(response)['version'], Stub.version)
        req = Request(self.url+'/ask', data=b'{"question":"CBA profit FY2025?"}', headers={'Content-Type':'application/json'})
        with urlopen(req) as response: result = json.load(response)
        self.assertEqual(result['generation']['status'], 'skipped'); self.assertEqual(result['route'], 'numeric')
        self.assertIn('Source-backed numbers', result['display_text'])


if __name__ == '__main__': unittest.main()
