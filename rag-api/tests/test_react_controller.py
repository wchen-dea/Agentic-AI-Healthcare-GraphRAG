from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from domain.models import RetrievalPlan
from domain.react_controller import ReactLoopSettings, run_react_query_loop


def _classify(_: str, patient_id: str | None):
    return "cohort_triage" if patient_id is None else "patient_summary"


def _select(request_type: str, question: str, patient_id: str | None, max_top_k: int):
    return RetrievalPlan(
        name=request_type,
        query_text=question,
        top_k=max(1, max_top_k),
        reason="test plan",
    )


def _rank_vector(items, _request_type):
    return items


def _rank_graph(items, _request_type):
    return items


def _synthesize(_question, vector_ctx, graph_ctx):
    return f"v={len(vector_ctx)} g={len(graph_ctx)}"


class ReactControllerTests(unittest.TestCase):
    def test_stops_on_confidence_after_dual_evidence(self) -> None:
        def vector_context(_q: str, _patient_id: str | None, _limit: int):
            return [{"event_id": "evt-1", "patient_id": "patient-1", "event_type": "note", "score": 0.9}]

        def graph_context(_patient_ids: list[str]):
            return [{"patient_id": "patient-1", "conditions": ["CKD"]}]

        result = run_react_query_loop(
            question="review risk",
            patient_id="patient-1",
            context_limit=3,
            settings=ReactLoopSettings(max_iterations=3, min_confidence=0.75, max_no_progress_steps=1),
            classify_request_type_fn=_classify,
            select_retrieval_plan_fn=_select,
            vector_context_fn=vector_context,
            rank_vector_context_fn=_rank_vector,
            graph_context_fn=graph_context,
            rank_graph_context_fn=_rank_graph,
            synthesize_answer_fn=_synthesize,
        )

        self.assertTrue(result["react"]["enabled"])
        self.assertEqual(result["react"]["final_reason"], "confidence_reached")
        self.assertEqual(result["react"]["iterations"], 1)
        self.assertEqual(len(result["vector_context"]), 1)
        self.assertEqual(len(result["graph_context"]), 1)

    def test_stops_on_max_iterations(self) -> None:
        def vector_context(_q: str, _patient_id: str | None, _limit: int):
            return []

        def graph_context(_patient_ids: list[str]):
            return []

        result = run_react_query_loop(
            question="no evidence",
            patient_id=None,
            context_limit=2,
            settings=ReactLoopSettings(max_iterations=2, min_confidence=1.0, max_no_progress_steps=5),
            classify_request_type_fn=_classify,
            select_retrieval_plan_fn=_select,
            vector_context_fn=vector_context,
            rank_vector_context_fn=_rank_vector,
            graph_context_fn=graph_context,
            rank_graph_context_fn=_rank_graph,
            synthesize_answer_fn=_synthesize,
        )

        self.assertEqual(result["react"]["final_reason"], "max_iterations_reached")
        self.assertEqual(result["react"]["iterations"], 2)
        self.assertEqual(result["react"]["confidence"], 0.0)

    def test_no_progress_limit_triggers_stop(self) -> None:
        def vector_context(_q: str, _patient_id: str | None, _limit: int):
            return [{"event_id": "evt-1", "patient_id": "patient-1", "event_type": "note", "score": 0.7}]

        def graph_context(_patient_ids: list[str]):
            return [{"patient_id": "patient-1", "conditions": ["A"]}]

        result = run_react_query_loop(
            question="repeat evidence",
            patient_id="patient-1",
            context_limit=4,
            settings=ReactLoopSettings(max_iterations=5, min_confidence=1.1, max_no_progress_steps=0),
            classify_request_type_fn=_classify,
            select_retrieval_plan_fn=_select,
            vector_context_fn=vector_context,
            rank_vector_context_fn=_rank_vector,
            graph_context_fn=graph_context,
            rank_graph_context_fn=_rank_graph,
            synthesize_answer_fn=_synthesize,
        )

        self.assertEqual(result["react"]["final_reason"], "no_progress_limit")
        self.assertEqual(result["react"]["iterations"], 2)
        self.assertEqual(len(result["vector_context"]), 1)
        self.assertEqual(len(result["graph_context"]), 1)


if __name__ == "__main__":
    unittest.main()
