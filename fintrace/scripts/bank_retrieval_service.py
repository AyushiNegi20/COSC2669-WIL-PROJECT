"""Warm, process-local retrieval service using unchanged v7 ranking semantics."""
from collections import OrderedDict
import contextlib
import io
from bank_retrieval import Encoder,tokenizer_for
from bank_retrieval_v4 import build_view,vectors_for
from bank_retrieval_v5 import normalise_question,semantic_focus
from bank_retrieval_v7 import RequestPlanner,RequestRetriever,plan_question
from bank_integrity import verify


class RetrievalService:
    def __init__(self):
        if not verify()['unchanged']: raise ValueError('Tested v7 foundation changed')
        self.encoder=None;self.engine=None;self.planner=None;self.cache=OrderedDict()

    def retrieve(self,question):
        empty={'records':[],'text':'','tokens':0,'omissions':[],'request_coverage':{}}
        p=plan_question(question)
        if p['behavior']!='answer' and not (p.get('reason') or '').startswith('The requested measure is not clear enough'):
            return p,empty
        if question in self.cache: vectors=self.cache[question]
        else:
            if self.encoder is None: self.encoder=Encoder('qwen')
            with contextlib.redirect_stdout(io.StringIO()):
                vectors=self.encoder.encode([normalise_question(question)[0],semantic_focus(question)],query=True)
            self.cache[question]=vectors
            if len(self.cache)>128: self.cache.popitem(last=False)
        if self.planner is None: self.planner=RequestPlanner()
        p=self.planner.plan(question,vectors[1])
        if p['behavior']!='answer': return p,empty
        if self.engine is None:
            records,units=build_view();self.engine=RequestRetriever(records,units,vectors_for(records))
            self.tokenizer=tokenizer_for('qwen')
        result=self.engine.search_plan(p,vectors[0],'hybrid')
        return result['plan'],self.engine.context(result,self.tokenizer)
