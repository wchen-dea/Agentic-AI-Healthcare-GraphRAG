from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class RagApiContractTests(unittest.TestCase):
    managed_env_keys = {
        "RAG_API_AUDIT_LOG_PATH",
        "RAG_API_DEFAULT_CALLER_ROLE",
        "RAG_API_MAX_RESPONSE_BYTES",
        "RAG_API_MAX_EVIDENCE_CHARS",
        "RAG_API_MAX_ANSWER_CHARS",
        "RAG_API_MAX_CONTEXT_ITEMS",
        "RAG_API_TOOL_POLICY_PATH",
        "LLM_MAX_TOKENS",
        "LLM_TIMEOUT_SECONDS",
    }

    def setUp(self) -> None:
        self.previous_env = {key: os.environ.get(key) for key in self.managed_env_keys}
        self.tmpdir = tempfile.TemporaryDirectory()
        self.policy_path = Path(self.tmpdir.name) / "tool_policies.json"
        self.policy_path.write_text(
            json.dumps(
                {
                    "roles": {
                        "read_only": ["patient_context_get", "vector_evidence_search"],
                        "generation": ["query", "graphrag_answer_generate", "risk_summary_generate"],
                        "export": ["evidence_bundle_export"],
                    }
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.tmpdir.cleanup()
        for key, value in self.previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        module = sys.modules.pop("app", None)
        if module is not None and hasattr(module, "neo4j"):
            module.neo4j.close()

    def load_module(self, **env_overrides):
        for key in self.managed_env_keys:
            os.environ.pop(key, None)
        for key, value in env_overrides.items():
            os.environ[key] = str(value)

        sys.modules.pop("app", None)
        return importlib.import_module("app")

    def test_query_redacts_vector_text_and_writes_audit_log(self) -> None:
        audit_path = Path(self.tmpdir.name) / "query-audit.log"
        rag_app = self.load_module(
            RAG_API_AUDIT_LOG_PATH=str(audit_path),
            RAG_API_TOOL_POLICY_PATH=str(self.policy_path),
        )
        client = TestClient(rag_app.app)

        with patch.object(
            rag_app,
            "vector_context",
            return_value=[
                {
                    "score": 0.98,
                    "event_id": "evt-1",
                    "patient_id": "patient-1",
                    "event_type": "lab_result",
                    "text": "Serum potassium elevated with note details that should be redacted.",
                }
            ],
        ), patch.object(
            rag_app,
            "graph_context",
            return_value=[{"patient_id": "patient-1", "conditions": ["CKD"]}],
        ), patch.object(rag_app, "ask_ollama", return_value="Bounded answer"):
            response = client.post(
                "/query",
                json={"question": "Summarize potassium risk", "patient_id": "patient-1"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["answer"], "Bounded answer")
        self.assertNotIn("text", payload["vector_context"][0])
        self.assertTrue(payload["vector_context"][0]["text_redacted"])
        self.assertEqual(payload["guardrails"]["evidence_access_level"], "none")
        self.assertTrue(audit_path.exists())

        audit_event = json.loads(audit_path.read_text(encoding="utf-8").strip())
        self.assertEqual(audit_event["tool_name"], "query")
        self.assertEqual(audit_event["outcome"], "success")
        self.assertEqual(audit_event["patient_scope"], ["patient-1"])
        self.assertEqual(audit_event["caller_id"], "role:generation")

    def test_query_enforces_role_policy(self) -> None:
        rag_app = self.load_module(
            RAG_API_AUDIT_LOG_PATH=str(Path(self.tmpdir.name) / "auth-audit.log"),
            RAG_API_TOOL_POLICY_PATH=str(self.policy_path),
        )
        client = TestClient(rag_app.app)

        response = client.post(
            "/query",
            json={"question": "Need role now"},
            headers={"X-Caller-Role": "read_only"},
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            response.json()["detail"],
            "Role 'read_only' is not authorized for tool 'query'",
        )

        with patch.object(rag_app, "vector_context", return_value=[]), patch.object(
            rag_app, "graph_context", return_value=[]
        ), patch.object(rag_app, "ask_ollama", return_value="Authorized"):
            ok_response = client.post(
                "/query",
                json={"question": "Need role now"},
                headers={"X-Caller-Role": "generation"},
            )

        self.assertEqual(ok_response.status_code, 200)
        self.assertEqual(ok_response.json()["answer"], "Authorized")

    def test_mcp_export_defaults_to_bounded_text_and_denies_raw_payload(self) -> None:
        rag_app = self.load_module(
            RAG_API_AUDIT_LOG_PATH=str(Path(self.tmpdir.name) / "mcp-audit.log"),
            RAG_API_MAX_EVIDENCE_CHARS="16",
            RAG_API_MAX_CONTEXT_ITEMS="2",
            RAG_API_TOOL_POLICY_PATH=str(self.policy_path),
        )

        fake_result = {
            "question": "Explain evidence",
            "patients": ["patient-1"],
            "vector_context": [
                {
                    "score": 0.8,
                    "event_id": "evt-9",
                    "patient_id": "patient-1",
                    "event_type": "note",
                    "text": "This evidence payload is longer than the configured budget.",
                }
            ],
            "graph_context": [
                {
                    "patient_id": "patient-1",
                    "conditions": ["CKD", "HF", "HTN"],
                    "observations": [
                        {"name": "sodium", "value": "134", "unit": "mmol/L"},
                        {"name": "potassium", "value": "5.7", "unit": "mmol/L"},
                        {"name": "creatinine", "value": "2.1", "unit": "mg/dL"},
                    ],
                }
            ],
            "answer": "done",
        }

        with patch.object(rag_app, "run_query", return_value=fake_result):
            bounded = rag_app.evidence_bundle_export("Explain evidence", patient_id="patient-1")
            raw_requested = rag_app.evidence_bundle_export(
                "Explain evidence",
                patient_id="patient-1",
                include_raw_payload=True,
            )

        self.assertEqual(bounded["vector_context"][0]["text"], "This evidence...")
        self.assertFalse(bounded["guardrails"]["evidence_text_redacted"])
        self.assertEqual(bounded["guardrails"]["evidence_access_level"], "bounded")
        self.assertEqual(bounded["guardrails"]["graph_access_level"], "broader")
        self.assertEqual(len(bounded["graph_context"][0]["conditions"]), 3)
        self.assertEqual(raw_requested["vector_context"][0]["text"], "This evidence...")
        self.assertTrue(raw_requested["guardrails"]["raw_payload_requested"])
        self.assertFalse(raw_requested["guardrails"]["raw_payload_returned"])

    def test_generation_and_export_have_different_evidence_defaults(self) -> None:
        rag_app = self.load_module(
            RAG_API_AUDIT_LOG_PATH=str(Path(self.tmpdir.name) / "role-audit.log"),
            RAG_API_MAX_EVIDENCE_CHARS="18",
            RAG_API_TOOL_POLICY_PATH=str(self.policy_path),
        )

        fake_result = {
            "question": "Compare defaults",
            "patients": ["patient-7"],
            "vector_context": [
                {
                    "score": 0.75,
                    "event_id": "evt-7",
                    "patient_id": "patient-7",
                    "event_type": "clinical_note",
                    "text": "Detailed clinical note evidence for export callers.",
                }
            ],
            "graph_context": [],
            "answer": "done",
        }

        with patch.object(rag_app, "run_query", return_value=fake_result):
            generation = rag_app.graphrag_answer_generate("Compare defaults", patient_id="patient-7")
            export = rag_app.evidence_bundle_export("Compare defaults", patient_id="patient-7")

        self.assertNotIn("text", generation["vector_context"][0])
        self.assertEqual(generation["guardrails"]["evidence_access_level"], "none")
        self.assertEqual(generation["guardrails"]["graph_access_level"], "standard")
        self.assertEqual(export["vector_context"][0]["text"], "Detailed clinic...")
        self.assertEqual(export["guardrails"]["evidence_access_level"], "bounded")
        self.assertEqual(export["guardrails"]["graph_access_level"], "broader")

    def test_query_accepts_explicit_generation_role_header(self) -> None:
        rag_app = self.load_module(
            RAG_API_AUDIT_LOG_PATH=str(Path(self.tmpdir.name) / "header-audit.log"),
            RAG_API_TOOL_POLICY_PATH=str(self.policy_path),
        )
        client = TestClient(rag_app.app)

        with patch.object(rag_app, "vector_context", return_value=[]), patch.object(
            rag_app, "graph_context", return_value=[]
        ), patch.object(rag_app, "ask_ollama", return_value="Header role accepted"):
            response = client.post(
                "/query",
                json={"question": "Header role check"},
                headers={"X-Caller-Role": "generation"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["answer"], "Header role accepted")

    def test_query_trims_response_to_configured_budget(self) -> None:
        rag_app = self.load_module(
            RAG_API_AUDIT_LOG_PATH=str(Path(self.tmpdir.name) / "budget-audit.log"),
            RAG_API_MAX_RESPONSE_BYTES="750",
            RAG_API_MAX_ANSWER_CHARS="400",
            RAG_API_MAX_CONTEXT_ITEMS="5",
            RAG_API_TOOL_POLICY_PATH=str(self.policy_path),
        )
        client = TestClient(rag_app.app)

        vector_items = [
            {
                "score": 0.7,
                "event_id": f"evt-{index}",
                "patient_id": "patient-2",
                "event_type": "telemetry",
                "text": f"telemetry payload {index}",
            }
            for index in range(5)
        ]
        graph_items = [
            {"patient_id": "patient-2", "conditions": [f"condition-{index}"]}
            for index in range(5)
        ]

        with patch.object(rag_app, "vector_context", return_value=vector_items), patch.object(
            rag_app, "graph_context", return_value=graph_items
        ), patch.object(rag_app, "ask_ollama", return_value="A" * 400):
            response = client.post(
                "/query",
                json={"question": "Trim oversized response", "patient_id": "patient-2"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.assertLessEqual(len(encoded), 750)
        self.assertTrue(payload["guardrails"]["response_truncated"])


if __name__ == "__main__":
    unittest.main()
