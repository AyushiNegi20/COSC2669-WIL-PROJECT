from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from threading import Thread
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from serve_fintrace_web import handler_for


class Stub:
    def answer(self,q): return {'question':q,'answer':{'status':'clarify','message':'Specify the bank and basis.'}}


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=TemporaryDirectory();cls.root=Path(cls.temp.name)
        for name in ['web','config','data/raw']: (cls.root/name).mkdir(parents=True,exist_ok=True)
        for file in ['index.html','app.css','app.mjs','ui-model.mjs','favicon.svg']:
            (cls.root/'web'/file).write_text('fixture '+file,encoding='utf-8')
        cls.pdf=cls.root/'data/raw/fixture.pdf';cls.data=b'%PDF-test-fixture';cls.pdf.write_bytes(cls.data)
        (cls.root/'config/banking_sources.json').write_text(json.dumps({'documents':[{
            'id':'cba25','company':'CBA','report_year':2025,'period_end':'2025-06-30',
            'title':'Fixture report','role':'primary','file':'fixture.pdf','sha256':sha256(cls.data).hexdigest()}]}))
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler_for(Stub(),cls.root))
        cls.worker=Thread(target=cls.server.serve_forever,daemon=True);cls.worker.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.worker.join();cls.temp.cleanup()

    def test_static_assets_and_security_headers(self):
        for path,kind in [('/','text/html'),('/app.mjs','text/javascript'),('/app.css','text/css')]:
            with urlopen(self.url+path) as response:
                self.assertTrue(response.headers['Content-Type'].startswith(kind))
                self.assertEqual(response.headers['X-Content-Type-Options'],'nosniff')
                self.assertIn("script-src 'self'",response.headers['Content-Security-Policy'])

    def test_catalog_no_local_paths(self):
        with urlopen(self.url+'/documents') as response: payload=json.load(response)
        doc=payload['documents'][0]
        self.assertTrue(doc['available']);self.assertEqual(doc['path'],'/reports/cba25.pdf')
        self.assertNotIn(str(self.root),json.dumps(payload))

    def test_pdf_exact_source_bytes(self):
        with urlopen(self.url+'/reports/cba25.pdf') as response:
            self.assertEqual(response.read(),self.data)
            self.assertEqual(response.headers['Content-Type'],'application/pdf')

    def test_changed_pdf_is_not_served(self):
        self.pdf.write_bytes(b'changed')
        try:
            with self.assertRaises(HTTPError) as caught: urlopen(self.url+'/reports/cba25.pdf')
            self.assertEqual(caught.exception.code,409)
        finally: self.pdf.write_bytes(self.data)

    def test_no_directory_listing_or_arbitrary_files(self):
        for path in ['/scripts/answer_bank_v9.py','/../config/banking_sources.json','/%2e%2e/config/banking_sources.json','/reports/unknown.pdf','/web/']:
            with self.subTest(path=path),self.assertRaises(HTTPError) as caught: urlopen(self.url+path)
            self.assertEqual(caught.exception.code,404)

    def test_rebinding_host_rejected(self):
        with self.assertRaises(HTTPError) as caught:
            urlopen(Request(self.url+'/',headers={'Host':'attacker.example'}))
        self.assertEqual(caught.exception.code,403)

    def test_same_origin_api_and_cross_origin_refusal(self):
        req=Request(self.url+'/ask',json.dumps({'question':'Profit?'}).encode(),{'Content-Type':'application/json','Origin':self.url})
        with urlopen(req) as response: self.assertEqual(json.load(response)['answer']['status'],'clarify')
        req=Request(self.url+'/ask',b'{"question":"Profit?"}',{'Content-Type':'application/json','Origin':'http://localhost:12345'})
        with self.assertRaises(HTTPError) as caught: urlopen(req)
        self.assertEqual(caught.exception.code,403)

    def test_health_is_existing_backend_version(self):
        with urlopen(self.url+'/health') as response: self.assertEqual(json.load(response)['version'],'v9-demo')


if __name__=='__main__': unittest.main()
