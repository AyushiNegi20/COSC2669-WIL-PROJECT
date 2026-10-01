from http.server import BaseHTTPRequestHandler
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from serve_fintrace_release import ExclusiveLocalServer


class ExclusiveServerTests(unittest.TestCase):
    def test_second_server_cannot_share_port(self):
        with ExclusiveLocalServer(('127.0.0.1', 0), BaseHTTPRequestHandler) as first:
            with self.assertRaises(OSError):
                with ExclusiveLocalServer(first.server_address, BaseHTTPRequestHandler):
                    self.fail('A second server acquired the live demo port')


if __name__ == '__main__':
    unittest.main()
