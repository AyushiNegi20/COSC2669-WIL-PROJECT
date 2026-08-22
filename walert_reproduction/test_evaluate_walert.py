import unittest

from evaluate_walert import aggregate_metrics, per_query_metrics, topic_id


class EvaluationTests(unittest.TestCase):
    def test_perfect_ranking_has_perfect_cutoff_metrics(self):
        metrics = per_query_metrics({"P1": 2, "P2": 1}, ["P1", "P2"], (1, 2))
        self.assertEqual(metrics["mrr"], 1.0)
        self.assertEqual(metrics["ndcg@1"], 1.0)
        self.assertEqual(metrics["ndcg@2"], 1.0)
        self.assertEqual(metrics["hit@2"], 1.0)

    def test_missing_run_is_counted_as_zero(self):
        result = aggregate_metrics({"W01Q01": {"P1": 2}}, {}, lambda _: True)
        self.assertEqual(result["questions"], 1)
        self.assertEqual(result["queries_with_results"], 0)
        self.assertEqual(result["mrr"], 0.0)
        self.assertEqual(result["hit@5"], 0.0)

    def test_topic_ids_are_normalised(self):
        self.assertEqual(topic_id("W1Q1"), "W01")
        self.assertEqual(topic_id("W43Q1"), "W43")


if __name__ == "__main__":
    unittest.main()
