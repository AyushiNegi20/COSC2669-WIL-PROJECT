"""Download exactly the issuer PDFs in the banking manifest; verify before use."""
import hashlib
import urllib.request
from pathlib import Path

from extract_bank_reports import ROOT, read


def main():
    for doc in read(ROOT/'config/banking_sources.json')['documents']:
        path=ROOT/'data/raw'/doc['file']
        if path.exists():
            data=path.read_bytes()
        else:
            request=urllib.request.Request(doc['url'],headers={'User-Agent':'FinTrace academic source audit'})
            with urllib.request.urlopen(request,timeout=90) as response:
                data=response.read()
            if not data.startswith(b'%PDF-') or hashlib.sha256(data).hexdigest()!=doc['sha256']:
                raise ValueError(f"Downloaded content differs for {doc['id']}; do not bypass verification")
            path.parent.mkdir(parents=True,exist_ok=True)
            temporary=path.with_suffix('.pdf.download')
            temporary.write_bytes(data)
            temporary.replace(path)
        if hashlib.sha256(data).hexdigest()!=doc['sha256']:
            raise ValueError(f"Existing source differs: {doc['id']}")
        print(f"Verified {doc['id']}: {len(data)} bytes")


if __name__=='__main__':
    main()
