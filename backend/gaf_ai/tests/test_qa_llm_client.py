"""Tests for OpenAIClient HTTP integration (migrated from qa app — 2026-08-04).

Covers OpenAIClient:
- chat() with mocked requests.post (success path)
- chat() raises LLMTimeoutError on requests.Timeout
- chat() raises LLMAPIError on HTTP error (raise_for_status)
- chat() raises LLMAPIError on JSON parse error
- chat() parses choices[0].message.content correctly
- chat() parses usage tokens correctly
- chat() forwards model/temperature/max_tokens/kwargs in payload
- chat() sends Bearer auth header
- stream_chat() yields content chunks from SSE lines
- stream_chat() raises LLMTimeoutError on timeout
- stream_chat() raises LLMAPIError on HTTP error
- stream_chat() stops at [DONE] marker
- stream_chat() skips malformed JSON chunks
- LLMClient backward-compat alias
- MODEL_CONFIGS defaults for openai/deepseek/custom
"""
import json
from unittest.mock import MagicMock, patch

import pytest
import requests
from django.test import SimpleTestCase

from gaf_ai.qa_llm_client import (
    MODEL_CONFIGS,
    LLMAPIError,
    LLMClient,
    LLMTimeoutError,
    OpenAIClient,
)

pytestmark = pytest.mark.unit


def _mock_response(json_data=None, status_code=200, content=None):
    """Build a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data or {}
    resp.content = content if content is not None else (json.dumps(json_data or {}).encode())
    resp.raise_for_status = MagicMock(
        side_effect=requests.exceptions.HTTPError(response=resp) if status_code >= 400 else None
    )
    return resp


class OpenAIClientChatTest(SimpleTestCase):
    """Tests for OpenAIClient.chat() HTTP integration."""

    def _make_client(self, **kwargs):
        defaults = {
            'api_key': 'sk-test',
            'provider': 'custom',
            'base_url': 'https://fake.api/v1',
            'model': 'test-model',
            'timeout': 30,
        }
        defaults.update(kwargs)
        return OpenAIClient(**defaults)

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_success_returns_content_and_usage(self, mock_post):
        """Successful chat returns dict with content/usage/model."""
        mock_post.return_value = _mock_response({
            'choices': [{'message': {'content': 'Hello!'}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
            'model': 'test-model',
        })
        client = self._make_client()
        result = client.chat(messages=[{'role': 'user', 'content': 'hi'}])
        self.assertEqual(result['content'], 'Hello!')
        self.assertEqual(result['usage']['input_tokens'], 10)
        self.assertEqual(result['usage']['output_tokens'], 5)
        self.assertEqual(result['usage']['total_tokens'], 15)
        self.assertEqual(result['model'], 'test-model')

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_sends_bearer_auth_header(self, mock_post):
        """Authorization header should be 'Bearer {api_key}'."""
        mock_post.return_value = _mock_response({'choices': [{'message': {'content': 'ok'}}]})
        client = self._make_client(api_key='sk-secret')
        client.chat(messages=[{'role': 'user', 'content': 'hi'}])
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer sk-secret')
        self.assertEqual(kwargs['headers']['Content-Type'], 'application/json')

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_forwards_model_temperature_max_tokens(self, mock_post):
        """Payload should include model, messages, temperature, max_tokens."""
        mock_post.return_value = _mock_response({'choices': [{'message': {'content': 'ok'}}]})
        client = self._make_client()
        client.chat(
            messages=[{'role': 'user', 'content': 'hi'}],
            model='override-model',
            temperature=0.1,
            max_tokens=100,
        )
        _, kwargs = mock_post.call_args
        payload = kwargs['json']
        self.assertEqual(payload['model'], 'override-model')
        self.assertEqual(payload['temperature'], 0.1)
        self.assertEqual(payload['max_tokens'], 100)
        self.assertEqual(payload['messages'], [{'role': 'user', 'content': 'hi'}])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_uses_default_model_when_not_overridden(self, mock_post):
        """When model=None, the client's default model is used."""
        mock_post.return_value = _mock_response({'choices': [{'message': {'content': 'ok'}}]})
        client = self._make_client(model='default-m')
        client.chat(messages=[])
        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs['json']['model'], 'default-m')

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_timeout_raises_llm_timeout_error(self, mock_post):
        """requests.Timeout → LLMTimeoutError."""
        mock_post.side_effect = requests.exceptions.Timeout('timed out')
        client = self._make_client()
        with self.assertRaises(LLMTimeoutError):
            client.chat(messages=[])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_http_error_raises_llm_api_error(self, mock_post):
        """HTTP 4xx/5xx → LLMAPIError."""
        mock_post.side_effect = requests.exceptions.HTTPError('500 error')
        client = self._make_client()
        with self.assertRaises(LLMAPIError):
            client.chat(messages=[])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_json_parse_error_raises_llm_api_error(self, mock_post):
        """If response.json() fails, LLMAPIError is raised."""
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.side_effect = ValueError('not JSON')
        mock_post.return_value = resp
        client = self._make_client()
        with self.assertRaises(LLMAPIError):
            client.chat(messages=[])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_empty_choices_returns_empty_content(self, mock_post):
        """If choices array is empty, content should be ''."""
        mock_post.return_value = _mock_response({'choices': [], 'usage': {}})
        client = self._make_client()
        result = client.chat(messages=[])
        self.assertEqual(result['content'], '')

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_missing_choices_key_returns_empty_content(self, mock_post):
        """If 'choices' key is missing entirely, content should be ''."""
        mock_post.return_value = _mock_response({})
        client = self._make_client()
        result = client.chat(messages=[])
        self.assertEqual(result['content'], '')

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_chat_extra_kwargs_included_in_payload(self, mock_post):
        """Extra kwargs (e.g. top_p) should be added to the payload."""
        mock_post.return_value = _mock_response({'choices': [{'message': {'content': 'ok'}}]})
        client = self._make_client()
        client.chat(messages=[], top_p=0.9, frequency_penalty=0.5)
        _, kwargs = mock_post.call_args
        payload = kwargs['json']
        self.assertEqual(payload['top_p'], 0.9)
        self.assertEqual(payload['frequency_penalty'], 0.5)


class OpenAIClientStreamChatTest(SimpleTestCase):
    """Tests for OpenAIClient.stream_chat() SSE parsing."""

    def _make_client(self, **kwargs):
        defaults = {
            'api_key': 'sk-test',
            'provider': 'custom',
            'base_url': 'https://fake.api/v1',
            'model': 'test-model',
            'timeout': 30,
        }
        defaults.update(kwargs)
        return OpenAIClient(**defaults)

    def _mock_stream_response(self, lines):
        """Mock a streaming response with SSE lines."""
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.iter_lines.return_value = [line.encode('utf-8') if isinstance(line, str) else line for line in lines]
        return resp

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_yields_content_chunks(self, mock_post):
        """SSE 'data: {...}' lines with delta.content are yielded."""
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'Hello'}}]}),
            'data: ' + json.dumps({'choices': [{'delta': {'content': ' world'}}]}),
            'data: [DONE]',
        ]
        mock_post.return_value = self._mock_stream_response(lines)
        client = self._make_client()
        chunks = list(client.stream_chat(messages=[]))
        self.assertEqual(chunks, ['Hello', ' world'])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_stops_at_done_marker(self, mock_post):
        """The [DONE] marker stops the stream."""
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'A'}}]}),
            'data: [DONE]',
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'should not appear'}}]}),
        ]
        mock_post.return_value = self._mock_stream_response(lines)
        client = self._make_client()
        chunks = list(client.stream_chat(messages=[]))
        self.assertEqual(chunks, ['A'])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_skips_empty_lines(self, mock_post):
        """Empty lines in the stream are skipped."""
        lines = ['', 'data: ' + json.dumps({'choices': [{'delta': {'content': 'X'}}]}), '', 'data: [DONE]']
        mock_post.return_value = self._mock_stream_response(lines)
        client = self._make_client()
        chunks = list(client.stream_chat(messages=[]))
        self.assertEqual(chunks, ['X'])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_skips_lines_without_data_prefix(self, mock_post):
        """Lines that don't start with 'data: ' are skipped."""
        lines = [
            ': comment line',
            'event: ping',
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'Y'}}]}),
            'data: [DONE]',
        ]
        mock_post.return_value = self._mock_stream_response(lines)
        client = self._make_client()
        chunks = list(client.stream_chat(messages=[]))
        self.assertEqual(chunks, ['Y'])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_skips_malformed_json(self, mock_post):
        """Malformed JSON chunks are skipped (no crash)."""
        lines = [
            'data: {broken json',
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'Z'}}]}),
            'data: [DONE]',
        ]
        mock_post.return_value = self._mock_stream_response(lines)
        client = self._make_client()
        chunks = list(client.stream_chat(messages=[]))
        self.assertEqual(chunks, ['Z'])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_skips_chunks_with_no_content(self, mock_post):
        """Chunks where delta.content is empty/missing are skipped."""
        lines = [
            'data: ' + json.dumps({'choices': [{'delta': {'role': 'assistant'}}]}),
            'data: ' + json.dumps({'choices': [{'delta': {'content': ''}}]}),
            'data: ' + json.dumps({'choices': [{'delta': {'content': 'real'}}]}),
            'data: [DONE]',
        ]
        mock_post.return_value = self._mock_stream_response(lines)
        client = self._make_client()
        chunks = list(client.stream_chat(messages=[]))
        self.assertEqual(chunks, ['real'])

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_timeout_raises_llm_timeout_error(self, mock_post):
        """requests.Timeout → LLMTimeoutError."""
        mock_post.side_effect = requests.exceptions.Timeout('timed out')
        client = self._make_client()
        with self.assertRaises(LLMTimeoutError):
            list(client.stream_chat(messages=[]))

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_http_error_raises_llm_api_error(self, mock_post):
        """HTTP error → LLMAPIError."""
        mock_post.side_effect = requests.exceptions.HTTPError('502')
        client = self._make_client()
        with self.assertRaises(LLMAPIError):
            list(client.stream_chat(messages=[]))

    @patch('gaf_ai.qa_llm_client.requests.post')
    def test_stream_payload_includes_stream_true(self, mock_post):
        """The stream payload should include 'stream': True."""
        mock_post.return_value = self._mock_stream_response(['data: [DONE]'])
        client = self._make_client()
        list(client.stream_chat(messages=[]))
        _, kwargs = mock_post.call_args
        self.assertTrue(kwargs['json']['stream'])
        self.assertTrue(kwargs['stream'])


class ModelConfigsTest(SimpleTestCase):
    """Tests for MODEL_CONFIGS defaults and LLMClient alias."""

    def test_openai_config(self):
        cfg = MODEL_CONFIGS['openai']
        self.assertEqual(cfg['base_url'], 'https://api.openai.com/v1')
        self.assertEqual(cfg['chat_endpoint'], '/chat/completions')
        self.assertEqual(cfg['default_model'], 'gpt-4o')

    def test_deepseek_config(self):
        cfg = MODEL_CONFIGS['deepseek']
        self.assertEqual(cfg['base_url'], 'https://api.deepseek.com/v1')
        self.assertEqual(cfg['default_model'], 'deepseek-chat')

    def test_custom_config_has_empty_defaults(self):
        cfg = MODEL_CONFIGS['custom']
        self.assertEqual(cfg['base_url'], '')
        self.assertEqual(cfg['default_model'], '')

    def test_llm_client_alias_is_openai_client(self):
        """LLMClient is a backward-compat alias for OpenAIClient."""
        self.assertIs(LLMClient, OpenAIClient)

    def test_openai_client_uses_provider_config_defaults(self):
        """When base_url/model not passed, provider config defaults are used."""
        client = OpenAIClient(api_key='sk-x', provider='openai')
        self.assertEqual(client.base_url, 'https://api.openai.com/v1')
        self.assertEqual(client.model, 'gpt-4o')

    def test_openai_client_explicit_overrides(self):
        """Explicit base_url/model override provider config."""
        client = OpenAIClient(api_key='sk-x', provider='openai', base_url='https://custom.api/v1', model='custom-model')
        self.assertEqual(client.base_url, 'https://custom.api/v1')
        self.assertEqual(client.model, 'custom-model')

    def test_unknown_provider_falls_back_to_custom(self):
        """Unknown provider uses 'custom' config (empty defaults)."""
        client = OpenAIClient(api_key='sk-x', provider='unknown_provider')
        self.assertEqual(client.base_url, '')
        self.assertEqual(client.model, '')

    def test_chat_stream_alias_works(self):
        """chat_stream() is a deprecated alias for stream_chat()."""
        client = OpenAIClient(api_key='sk-x', provider='custom', base_url='https://fake', model='m')
        self.assertTrue(callable(getattr(client, 'chat_stream', None)))


class OpenAIClientPropertiesTest(SimpleTestCase):
    """Tests for OpenAIClient property accessors."""

    def test_provider_property(self):
        client = OpenAIClient(api_key='sk-x', provider='deepseek')
        self.assertEqual(client.provider, 'deepseek')

    def test_base_url_property(self):
        client = OpenAIClient(api_key='sk-x', provider='custom', base_url='https://my.api/v1')
        self.assertEqual(client.base_url, 'https://my.api/v1')

    def test_model_property(self):
        client = OpenAIClient(api_key='sk-x', provider='custom', model='my-model')
        self.assertEqual(client.model, 'my-model')

    def test_timeout_stored(self):
        client = OpenAIClient(api_key='sk-x', provider='custom', timeout=60)
        self.assertEqual(client._timeout, 60)
