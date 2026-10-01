"""V10 retrieval and arithmetic plus local, checked Qwen synthesis."""
import argparse
import json
from time import perf_counter
from answer_bank_v10 import Backend as EvidenceBackend
from answer_bank_v9 import display
from bank_generation_v11 import SynthesisClient, add_generation


class Backend:
    version = 'v11-generative-development'

    def __init__(self, evidence_backend=None, client=None):
        self.evidence_backend = evidence_backend if evidence_backend is not None else EvidenceBackend()
        self.client = client if client is not None else SynthesisClient()

    @property
    def binder(self):
        return self.evidence_backend.binder

    def answer(self, question):
        start = perf_counter()
        result = add_generation(self.evidence_backend.answer(question), self.client)
        result['version'] = self.version
        result['seconds'] = perf_counter() - start
        return result


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('question'); p.add_argument('--json', action='store_true')
    a = p.parse_args(); result = Backend().answer(a.question)
    print(json.dumps(result, indent=2) if a.json else display(result))
