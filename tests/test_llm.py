import os
import sys
from unittest.mock import patch, MagicMock

# Ensure app directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../app')))

from llm import LLM

def test_llm_gemini_url():
    # Test initialization
    gemini_llm = LLM(provider="gemini", model="gemini-3.5-flash", api_key="test-key")
    assert gemini_llm.provider == "gemini"
    assert gemini_llm.base_url == "https://generativelanguage.googleapis.com/v1beta/openai"

    openai_llm = LLM(provider="openai", model="gpt-4o", api_key="test-key")
    assert openai_llm.provider == "openai"
    assert openai_llm.base_url == "https://api.openai.com"

    # Test the constructed URL in _raw_chat for Gemini
    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}}]
        }
        mock_post.return_value = mock_response

        # Execute chat_json (which calls _raw_chat)
        res = gemini_llm.chat_json("system prompt", "user prompt")
        assert res == {"ok": True}

        # Check call arguments
        mock_post.assert_called_once()
        called_url = mock_post.call_args[0][0]
        # It should end with /chat/completions and NOT /v1/chat/completions
        assert called_url == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

    # Test the constructed URL in _raw_chat for OpenAI
    with patch("httpx.post") as mock_post:
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"ok": true}'}}]
        }
        mock_post.return_value = mock_response

        # Execute chat_json (which calls _raw_chat)
        res = openai_llm.chat_json("system prompt", "user prompt")
        assert res == {"ok": True}

        # Check call arguments
        mock_post.assert_called_once()
        called_url = mock_post.call_args[0][0]
        # It should contain /v1/chat/completions
        assert called_url == "https://api.openai.com/v1/chat/completions"
