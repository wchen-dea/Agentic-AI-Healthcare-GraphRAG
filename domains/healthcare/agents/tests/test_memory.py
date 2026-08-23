from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from domain.memory import (
    ConversationSession,
    RedisSessionStore,
    SessionStore,
    _deserialize_session,
    _serialize_session,
    generate_session_id,
)


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


if __name__ == "__main__":
    unittest.main()
