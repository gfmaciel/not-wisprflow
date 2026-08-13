import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from providers import GeminiProvider, MonoResult, OpenAIProvider


def test_mono_result_clamps_score():
    assert MonoResult.from_mapping({"text": " x ", "completion_score": 1.7}) == MonoResult("x", 1.0)
    assert MonoResult.from_mapping({"text": "x", "completion_score": -2}) == MonoResult("x", 0.0)


def test_openai_mono_uses_forced_function_call_and_context():
    provider = OpenAIProvider.__new__(OpenAIProvider)
    provider.client = MagicMock()
    tool_call = SimpleNamespace(
        function=SimpleNamespace(arguments=json.dumps({"text": "there.", "completion_score": 0.94}))
    )
    message = SimpleNamespace(tool_calls=[tool_call])
    provider.client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=message)]
    )

    result = provider.process_audio(
        b"wav",
        "gpt-audio-mini",
        "system",
        previous_context="Hello",
        temperature=0.0,
    )

    assert result == MonoResult("there.", 0.94)
    kwargs = provider.client.chat.completions.create.call_args.kwargs
    assert kwargs["tool_choice"]["function"]["name"] == "emit_transcript_result"
    assert kwargs["temperature"] == 0.0
    assert "Hello" in kwargs["messages"][1]["content"][0]["text"]


def test_gemini_mono_uses_json_schema_and_context():
    provider = GeminiProvider.__new__(GeminiProvider)
    provider.client = MagicMock()
    provider.client.models.generate_content.return_value = SimpleNamespace(
        text=json.dumps({"text": "done.", "completion_score": 0.91})
    )

    fake_types = SimpleNamespace(
        Part=SimpleNamespace(from_bytes=lambda **kwargs: ("audio", kwargs))
    )
    provider._types = lambda: fake_types

    result = provider.process_audio(
        b"wav",
        "gemini-3.6-flash",
        "system",
        previous_context="Earlier text",
        temperature=0.0,
    )

    assert result == MonoResult("done.", 0.91)
    kwargs = provider.client.models.generate_content.call_args.kwargs
    assert "Earlier text" in kwargs["contents"][0]
    assert kwargs["config"]["response_format"]["text"]["mime_type"] == "application/json"
    assert kwargs["config"]["temperature"] == 0.0
