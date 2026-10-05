from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock, patch

from healthcare_agent.orchestration.memory import (
    ConversationSession,
    InMemoryPatientMemoryStore,
    PatientMemoryFact,
    PatientMemoryPolicy,
    PatientMemoryRecord,
    RedisSessionStore,
    SessionStore,
    _deserialize_session,
    _serialize_session,
    generate_session_id,
)
from healthcare_agent.orchestration.graph import patient_memory_retrieval
from healthcare_agent.orchestration.query_service import QueryService


class SerializationTests(unittest.TestCase):
    def test_round_trip(self):
        session = ConversationSession("s1")
        session.add_turn(question="What meds?", answer="Warfarin", patient_id="p1")
        session.update_preferences(preferred_detail_level="detailed")

        data = _serialize_session(session)
        restored = _deserialize_session(data)

        self.assertEqual(restored.session_id, "s1")
        self.assertEqual(len(restored.turns), 1)
        self.assertEqual(restored.turns[0].question, "What meds?")
        self.assertEqual(restored.turns[0].patient_id, "p1")
        self.assertEqual(restored.preferences.preferred_detail_level, "detailed")

    def test_multiple_turns_preserved(self):
        session = ConversationSession("s2")
        session.add_turn(question="Q1", answer="A1")
        session.add_turn(question="Q2", answer="A2")
        session.add_turn(question="Q3", answer="A3")

        restored = _deserialize_session(_serialize_session(session))

        self.assertEqual(len(restored.turns), 3)
        self.assertEqual(restored.turns[2].question, "Q3")

    def test_empty_session_serializes(self):
        session = ConversationSession("empty")
        data = _serialize_session(session)
        restored = _deserialize_session(data)
        self.assertEqual(restored.session_id, "empty")
        self.assertEqual(len(restored.turns), 0)


class InMemorySessionStoreTests(unittest.TestCase):
    def test_get_or_create_returns_session(self):
        store = SessionStore()
        session = store.get_or_create("s1")
        self.assertEqual(session.session_id, "s1")

    def test_get_returns_none_for_unknown(self):
        store = SessionStore()
        self.assertIsNone(store.get("unknown"))


class RedisSessionStoreTests(unittest.TestCase):
    def _make_store(self, mock_client):
        """Create a RedisSessionStore with a mocked Redis client."""
        import types
        mock_redis = types.ModuleType("redis")
        mock_redis.Redis = MagicMock()
        mock_redis.Redis.from_url = MagicMock(return_value=mock_client)
        with patch.dict("sys.modules", {"redis": mock_redis}):
            store = RedisSessionStore(redis_url="redis://localhost:6379/0")
        return store

    def _mock_client(self):
        client = MagicMock()
        client.get.return_value = None
        client.keys.return_value = []
        return client

    def test_get_or_create_new_session(self):
        mock_client = self._mock_client()
        store = self._make_store(mock_client)

        session = store.get_or_create("new-session")

        self.assertEqual(session.session_id, "new-session")
        mock_client.setex.assert_called_once()

    def test_get_existing_session(self):
        original = ConversationSession("existing")
        original.add_turn(question="Q", answer="A", patient_id="p1")
        serialized = _serialize_session(original)

        mock_client = self._mock_client()
        mock_client.get.return_value = serialized
        store = self._make_store(mock_client)

        session = store.get("existing")

        self.assertIsNotNone(session)
        self.assertEqual(len(session.turns), 1)
        self.assertEqual(session.turns[0].question, "Q")

    def test_get_returns_none_for_missing(self):
        mock_client = self._mock_client()
        store = self._make_store(mock_client)

        self.assertIsNone(store.get("nonexistent"))

    def test_save_persists_session(self):
        mock_client = self._mock_client()
        store = self._make_store(mock_client)
        store._ttl = 7200

        session = ConversationSession("s1")
        session.add_turn(question="Q", answer="A")
        store.save(session)

        mock_client.setex.assert_called_once()
        args = mock_client.setex.call_args
        self.assertEqual(args[0][0], "session:s1")
        self.assertEqual(args[0][1], 7200)

    def test_delete_removes_key(self):
        mock_client = self._mock_client()
        store = self._make_store(mock_client)

        store.delete("s1")
        mock_client.delete.assert_called_once_with("session:s1")


class GenerateSessionIdTests(unittest.TestCase):
    def test_deterministic(self):
        id1 = generate_session_id("user1", "127.0.0.1")
        id2 = generate_session_id("user1", "127.0.0.1")
        self.assertEqual(id1, id2)

    def test_different_users_differ(self):
        id1 = generate_session_id("user1", "127.0.0.1")
        id2 = generate_session_id("user2", "127.0.0.1")
        self.assertNotEqual(id1, id2)


class DurablePatientMemoryTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryPatientMemoryStore()
        self.service = QueryService(max_context_items=5, patient_memory_store=self.store)

    def test_round_trip_and_provenance(self):
        record = self.service.write_patient_memory(
            "p1",
            [PatientMemoryFact(key=" Allergies ", value="  penicillin  ")],
            provenance={"source": "clinician_note"},
            consent=True,
        )

        loaded = self.service.load_patient_memory("p1")
        self.assertIsNotNone(loaded)
        self.assertEqual(record.patient_id, "p1")
        self.assertEqual(loaded.to_context()[0]["key"], "allergies")
        self.assertEqual(loaded.to_context()[0]["value"], "penicillin")
        self.assertEqual(
            loaded.to_context()[0]["metadata"]["provenance"]["source"],
            "clinician_note",
        )

    def test_consent_denied_write_rejected(self):
        with self.assertRaises(PermissionError):
            self.service.write_patient_memory(
                "p1",
                [PatientMemoryFact(key="risk", value="high")],
                provenance="assessment",
                consent=False,
            )
        self.assertIsNone(self.service.load_patient_memory("p1"))

    def test_expired_and_out_of_retention_facts_filtered(self):
        now = time.time()
        policy = PatientMemoryPolicy(retention_seconds=60, consent_granted=True)
        record = PatientMemoryRecord(
            patient_id="p1",
            policy=policy,
            facts=[
                PatientMemoryFact(key="expired", value="x", expires_at=now - 1),
                PatientMemoryFact(key="old", value="x", observed_at=now - 120),
                PatientMemoryFact(key="active", value="x", observed_at=now),
            ],
        )
        self.store.save(record)

        loaded = self.service.load_patient_memory("p1")
        self.assertEqual([fact.key for fact in loaded.active_facts()], ["active"])

    def test_patient_isolation(self):
        self.service.write_patient_memory(
            "p1", [PatientMemoryFact(key="condition", value="asthma")], "source-a", True
        )
        self.service.write_patient_memory(
            "p2", [PatientMemoryFact(key="condition", value="diabetes")], "source-b", True
        )

        self.assertEqual(self.service.load_patient_memory("p1").facts[0].value, "asthma")
        self.assertEqual(self.service.load_patient_memory("p2").facts[0].value, "diabetes")

    def test_graph_state_loads_and_deduplicates_patient_memory(self):
        record = PatientMemoryRecord(
            patient_id="p1",
            policy=PatientMemoryPolicy(consent_granted=True),
            facts=[PatientMemoryFact(fact_id="f1", key="risk", value="stable")],
        )
        state = {"_patient_memory_record": record}
        first = patient_memory_retrieval(state)
        second = patient_memory_retrieval(state)

        self.assertEqual(first["patient_memory_metadata"]["fact_count"], 1)
        self.assertEqual(
            first["patient_memory_context"],
            second["patient_memory_context"],
        )

    def test_policy_override_cannot_relax_configured_limits(self):
        service = QueryService(
            max_context_items=5,
            patient_memory_store=self.store,
            patient_memory_policy=PatientMemoryPolicy(
                consent_required=True,
                retention_seconds=60,
                max_facts=1,
            ),
        )
        with self.assertRaises(PermissionError):
            service.write_patient_memory(
                "p1",
                [PatientMemoryFact(key="risk", value="high")],
                "test",
                True,
                policy=PatientMemoryPolicy(
                    consent_required=False,
                    retention_seconds=3600,
                    max_facts=100,
                ),
            )

    def test_duplicate_fact_id_is_updated_not_duplicated(self):
        fact = PatientMemoryFact(fact_id="f1", key="risk", value="low")
        self.service.write_patient_memory("p1", [fact], "source-a", True)
        self.service.write_patient_memory(
            "p1",
            [PatientMemoryFact(fact_id="f1", key="risk", value="high")],
            "source-b",
            True,
        )

        loaded = self.service.load_patient_memory("p1")
        self.assertEqual(len(loaded.facts), 1)
        self.assertEqual(loaded.facts[0].value, "high")


if __name__ == "__main__":
    unittest.main()
