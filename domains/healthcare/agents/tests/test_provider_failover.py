"""Provider failover and model routing contract tests."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from llm_provider import AnthropicProvider, BedrockProvider, FallbackProvider, OllamaProvider, OpenAIProvider, create_provider


class FallbackProviderTests(unittest.TestCase):
    def test_primary_success_skips_fallback(self):
        primary = Mock()
        primary.generate.return_value = "Primary answer"
        fallback = Mock()
        fallback.generate.return_value = "Fallback answer"
        provider = FallbackProvider(primary, fallback)

        result = provider.generate(prompt="test", timeout_seconds=30, max_tokens=100)

        self.assertEqual(result, "Primary answer")
        fallback.generate.assert_not_called()

    def test_primary_error_triggers_fallback(self):
        primary = Mock()
        primary.generate.return_value = "LLM error: connection refused"
        fallback = Mock()
        fallback.generate.return_value = "Fallback answer"
        provider = FallbackProvider(primary, fallback)

        result = provider.generate(prompt="test", timeout_seconds=30, max_tokens=100)

        self.assertEqual(result, "Fallback answer")
        fallback.generate.assert_called_once()

    def test_both_fail_returns_fallback_error(self):
        primary = Mock()
        primary.generate.return_value = "LLM error: timeout"
        fallback = Mock()
        fallback.generate.return_value = "LLM error: also failed"
        provider = FallbackProvider(primary, fallback)

        result = provider.generate(prompt="test", timeout_seconds=30, max_tokens=100)

        self.assertEqual(result, "LLM error: also failed")


class OllamaProviderTests(unittest.TestCase):
    def _mock_available_model(self):
        """Mock the GET /api/tags call to return one available model."""
        mock_tags = Mock()
        mock_tags.status_code = 200
        mock_tags.json.return_value = {"models": [{"name": "test"}]}
        return mock_tags

    def test_timeout_returns_error_message(self):
        import requests
        provider = OllamaProvider(base_url="http://fake:11434", configured_model="test")
        with patch("llm_provider.requests.post", side_effect=requests.Timeout), \
             patch("llm_provider.requests.get", return_value=self._mock_available_model()):
            result = provider.generate(prompt="test", timeout_seconds=1, max_tokens=100)
        self.assertIn("timed out", result)

    def test_connection_error_returns_error_message(self):
        import requests
        provider = OllamaProvider(base_url="http://fake:11434", configured_model="test")
        with patch("llm_provider.requests.post", side_effect=requests.ConnectionError), \
             patch("llm_provider.requests.get", return_value=self._mock_available_model()):
            result = provider.generate(prompt="test", timeout_seconds=1, max_tokens=100)
        self.assertIn("unable to reach", result)

    def test_non_200_returns_error(self):
        provider = OllamaProvider(base_url="http://fake:11434", configured_model="test")
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "internal server error"
        with patch("llm_provider.requests.post", return_value=mock_response), \
             patch("llm_provider.requests.get") as mock_get:
            mock_tags = Mock()
            mock_tags.status_code = 200
            mock_tags.json.return_value = {"models": [{"name": "test"}]}
            mock_get.return_value = mock_tags
            result = provider.generate(prompt="test", timeout_seconds=1, max_tokens=100)
        self.assertIn("LLM error", result)

    def test_extra_kwargs_accepted(self):
        provider = OllamaProvider(base_url="http://fake:11434", configured_model="test")
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"response": "ok"}
        with patch("llm_provider.requests.post", return_value=mock_response), \
             patch("llm_provider.requests.get") as mock_get:
            mock_tags = Mock()
            mock_tags.status_code = 200
            mock_tags.json.return_value = {"models": [{"name": "test"}]}
            mock_get.return_value = mock_tags
            result = provider.generate(prompt="test", timeout_seconds=1, max_tokens=100, question="hello")
        self.assertEqual(result, "ok")


class OpenAIProviderTests(unittest.TestCase):
    @patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"})
    def test_timeout_returns_error(self):
        import requests
        provider = OpenAIProvider(configured_model="gpt-4")
        provider.api_key = "test-key"
        with patch("llm_provider.requests.post", side_effect=requests.Timeout):
            result = provider.generate(prompt="test", timeout_seconds=1, max_tokens=100)
        self.assertIn("timed out", result)

    def test_missing_api_key_returns_error(self):
        provider = OpenAIProvider(configured_model="gpt-4")
        provider.api_key = ""
        result = provider.generate(prompt="test", timeout_seconds=1, max_tokens=100)
        self.assertIn("OPENAI_API_KEY", result)


class AnthropicProviderTests(unittest.TestCase):
    def test_missing_api_key_returns_error(self):
        provider = AnthropicProvider(configured_model="claude-sonnet")
        provider.api_key = ""
        result = provider.generate(prompt="test", timeout_seconds=1, max_tokens=100)
        self.assertIn("ANTHROPIC_API_KEY", result)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"})
    def test_timeout_returns_error(self):
        import requests
        provider = AnthropicProvider(configured_model="claude-sonnet")
        provider.api_key = "test-key"
        with patch("llm_provider.requests.post", side_effect=requests.Timeout):
            result = provider.generate(prompt="test", timeout_seconds=1, max_tokens=100)
        self.assertIn("timed out", result)


class BedrockProviderTests(unittest.TestCase):
    def _mock_imports(self, client):
        def import_module(name):
            if name == "boto3":
                boto3 = Mock()
                boto3.client.return_value = client
                return boto3
            if name == "botocore.config":
                config_module = Mock()
                config_module.Config = Mock(return_value=Mock())
                return config_module
            raise ImportError(name)

        return patch("llm_provider.importlib.import_module", side_effect=import_module)

    def test_create_provider_supports_bedrock(self):
        provider = create_provider("bedrock", base_url="", configured_model="amazon.nova-pro-v1:0")

        self.assertIsInstance(provider, BedrockProvider)
        self.assertEqual(provider.model, "amazon.nova-pro-v1:0")

    def test_success_extracts_text_from_converse_response(self):
        client = Mock()
        client.converse.return_value = {
            "output": {"message": {"content": [{"text": "Bedrock answer"}]}}
        }
        provider = BedrockProvider(configured_model="anthropic.claude-3-5-haiku-20241022-v1:0")

        with self._mock_imports(client):
            result = provider.generate(prompt="test", timeout_seconds=30, max_tokens=100, temperature=0.1)

        self.assertEqual(result, "Bedrock answer")
        client.converse.assert_called_once()

    def test_missing_boto3_returns_error(self):
        provider = BedrockProvider(configured_model="amazon.nova-pro-v1:0")

        with patch("llm_provider.importlib.import_module", side_effect=ImportError("boto3")):
            result = provider.generate(prompt="test", timeout_seconds=30, max_tokens=100)

        self.assertIn("boto3 is required", result)

    def test_invalid_response_returns_error(self):
        client = Mock()
        client.converse.return_value = {"output": {"message": {"content": []}}}
        provider = BedrockProvider(configured_model="amazon.nova-pro-v1:0")

        with self._mock_imports(client):
            result = provider.generate(prompt="test", timeout_seconds=30, max_tokens=100)

        self.assertIn("invalid response format", result)


if __name__ == "__main__":
    unittest.main()
