"""Apply operation/scope constraints before unchanged hybrid ranking."""
from bank_retrieval_service import RetrievalService as V8Service
from bank_retrieval_v7 import RequestPlanner
from bank_operations_v9 import finish_plan


class Planner:
    def __init__(self): self.base=RequestPlanner()
    def plan(self,question,vector): return finish_plan(question,self.base.plan(question,vector))


class RetrievalService(V8Service):
    def __init__(self):
        super().__init__()
        self.planner=Planner()
