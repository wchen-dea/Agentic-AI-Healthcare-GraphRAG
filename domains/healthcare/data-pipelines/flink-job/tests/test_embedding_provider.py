from __future__ import annotations

import json
import math
import os
import unittest
import urllib.error
from unittest import mock

import helpers  # noqa: F401
from knowledge_core import embedding

FAKE_TOKEN = "dapi-test-secret-value"
_ENV_KEYS = (
    "EMBEDDING_PROVIDER",
    "EMBEDDING_DIM",
    "EMBEDDING_REQUIRE_MODEL",
    "DATABRICKS_HOST",
    "DATABRICKS_TOKEN",
    "DATABRICKS_EMBEDDING_ENDPOINT",
)


class _FakeResponse:
    def __init__(self, payload: dict):
        self._body = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def read(self) -> bytes:
        return self._body


def _payload(dim: int) -> dict:
    return {"data": [{"embedding": [float(i + 1) for i in range(dim)]}]}


class ProviderTestCase(unittest.TestCase):
    def setUp(self):
        self._saved = {key: os.environ.pop(key, None) for key in _ENV_KEYS}
        embedding._databricks_embed_cached.cache_clear()

    def tearDown(self):
        for key, value in self._saved.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value
        embedding._databricks_embed_cached.cache_clear()

    def _use_databricks(self, **extra: str):
        os.environ.update(
            {
                "EMBEDDING_PROVIDER": "databricks",
                "DATABRICKS_HOST": "adb-123.azuredatabricks.net",
                "DATABRICKS_TOKEN": FAKE_TOKEN,
                **extra,
            }
        )


class ProviderConfigTests(ProviderTestCase):
    def test_default_is_local_minilm_384(self):
        self.assertEqual(embedding.get_provider(), "local")
        self.assertEqual(embedding.get_vector_size(), 384)
        self.assertEqual(embedding.DEFAULT_MODEL, "sentence-transformers/all-MiniLM-L6-v2")

    def test_databricks_defaults_to_gte_large_1024(self):
        os.environ["EMBEDDING_PROVIDER"] = "databricks"
        self.assertEqual(embedding.get_vector_size(), 1024)
        self.assertEqual(embedding.DEFAULT_DATABRICKS_ENDPOINT, "databricks-gte-large-en")

    def test_embedding_dim_override(self):
        os.environ["EMBEDDING_DIM"] = "768"
        self.assertEqual(embedding.get_vector_size(), 768)

    def test_invalid_dim_rejected(self):
        os.environ["EMBEDDING_DIM"] = "0"
        with self.assertRaises(ValueError):
            embedding.get_vector_size()

    def test_unknown_provider_rejected(self):
        os.environ["EMBEDDING_PROVIDER"] = "openai"
        with self.assertRaises(ValueError):
            embedding.get_provider()


class DatabricksProviderTests(ProviderTestCase):
    def test_calls_serving_endpoint_and_normalizes(self):
        self._use_databricks()
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(_payload(1024))) as urlopen:
            vec = embedding.stable_embedding("chest pain", domain="clinical")

        request = urlopen.call_args.args[0]
        self.assertEqual(
            request.full_url,
            "https://adb-123.azuredatabricks.net/serving-endpoints/databricks-gte-large-en/invocations",
        )
        self.assertEqual(json.loads(request.data), {"input": ["chest pain"]})
        self.assertEqual(request.get_header("Authorization"), f"Bearer {FAKE_TOKEN}")
        self.assertEqual(len(vec), 1024)
        self.assertAlmostEqual(math.sqrt(sum(x * x for x in vec)), 1.0, places=6)

    def test_results_are_cached(self):
        self._use_databricks()
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(_payload(1024))) as urlopen:
            embedding.stable_embedding("same text")
            embedding.stable_embedding("same text")
        self.assertEqual(urlopen.call_count, 1)

    def test_custom_endpoint(self):
        self._use_databricks(DATABRICKS_EMBEDDING_ENDPOINT="my-embedder", EMBEDDING_DIM="8")
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(_payload(8))) as urlopen:
            vec = embedding.stable_embedding("x")
        self.assertIn("/serving-endpoints/my-embedder/invocations", urlopen.call_args.args[0].full_url)
        self.assertEqual(len(vec), 8)

    def test_dimension_mismatch_raises_in_strict_mode(self):
        self._use_databricks(EMBEDDING_REQUIRE_MODEL="true")
        with mock.patch("urllib.request.urlopen", return_value=_FakeResponse(_payload(384))):
            with self.assertRaisesRegex(RuntimeError, "EMBEDDING_DIM"):
                embedding.stable_embedding("x")

    def test_http_error_falls_back_to_md5_when_not_strict(self):
        self._use_databricks()
        error = urllib.error.HTTPError("https://x", 503, "unavailable", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            vec = embedding.stable_embedding("supplier delay")
        self.assertEqual(vec, embedding._md5_embedding("supplier delay", 1024))

    def test_http_error_raises_in_strict_mode_without_leaking_token(self):
        self._use_databricks(EMBEDDING_REQUIRE_MODEL="true")
        error = urllib.error.HTTPError("https://x", 401, "unauthorized", {}, None)
        with mock.patch("urllib.request.urlopen", side_effect=error):
            with self.assertRaises(RuntimeError) as ctx:
                embedding.stable_embedding("x")
        self.assertIn("401", str(ctx.exception))
        self.assertNotIn(FAKE_TOKEN, str(ctx.exception))
        self.assertIsNone(ctx.exception.__cause__)

    def test_missing_credentials_raise_in_strict_mode(self):
        os.environ.update({"EMBEDDING_PROVIDER": "databricks", "EMBEDDING_REQUIRE_MODEL": "true"})
        with self.assertRaisesRegex(RuntimeError, "DATABRICKS_TOKEN"):
            embedding.stable_embedding("x")
        os.environ["DATABRICKS_TOKEN"] = FAKE_TOKEN
        with self.assertRaisesRegex(RuntimeError, "DATABRICKS_HOST"):
            embedding.stable_embedding("x")


if __name__ == "__main__":
    unittest.main()
