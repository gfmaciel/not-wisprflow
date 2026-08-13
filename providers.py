from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from typing import Iterator, Optional


@dataclass(frozen=True)
class MonoResult:
    text: str
    completion_score: float

    @classmethod
    def from_mapping(cls, data: dict) -> "MonoResult":
        text = str(data.get("text", "")).strip()
        try:
            score = float(data.get("completion_score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        return cls(text=text, completion_score=max(0.0, min(1.0, score)))


_MONO_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": (
                "Cleaned transcript of ONLY the current audio chunk. "
                "Never repeat the previous context."
            ),
        },
        "completion_score": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": (
                "Confidence that the unfinished previous context plus the current chunk "
                "now form a semantically complete thought that can be pasted without "
                "waiting for more speech. 0 means clearly incomplete; 1 means clearly complete."
            ),
        },
    },
    "required": ["text", "completion_score"],
    "additionalProperties": False,
}


def _mono_user_instruction(previous_context: str) -> str:
    if previous_context:
        context = (
            "Previous unfinished transcript context (continuity only; DO NOT repeat it):\n"
            f"{previous_context}\n\n"
        )
    else:
        context = "There is no previous unfinished transcript context.\n\n"
    return (
        context
        + "Transcribe ONLY the supplied current audio chunk and clean it according to the "
        "system rules. Then score whether the combined thought (previous context + current "
        "chunk) is semantically complete. Return the current chunk text only."
    )


class GroqProvider:
    def __init__(self, api_key: str):
        from groq import Groq
        self.client = Groq(api_key=api_key)

    def transcribe(self, wav_bytes: bytes, model: str, language: Optional[str] = None) -> str:
        kwargs = {
            "file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav"),
            "model": model,
            "response_format": "text",
        }
        if language:
            kwargs["language"] = language
        result = self.client.audio.transcriptions.create(**kwargs)
        return result.strip() if isinstance(result, str) else result.text.strip()

    def cleanup(self, text: str, model: str, system_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        )
        return response.choices[0].message.content.strip()

    def stream_cleanup(self, text: str, model: str, system_prompt: str) -> Iterator[str]:
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            stream=True,
        )
        for event in response:
            delta = event.choices[0].delta.content or ""
            if delta:
                yield delta

    def process_audio(self, *args, **kwargs) -> MonoResult:
        raise ValueError("Groq is not supported for PROCESSING_MODE=mono; use OpenAI or Gemini.")


class OpenAIProvider:
    def __init__(self, api_key: str):
        from openai import OpenAI
        self.client = OpenAI(api_key=api_key)

    def transcribe(self, wav_bytes: bytes, model: str, language: Optional[str] = None) -> str:
        kwargs = {
            "file": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav"),
            "model": model,
        }
        if language:
            kwargs["language"] = language
        result = self.client.audio.transcriptions.create(**kwargs)
        return result.strip() if isinstance(result, str) else result.text.strip()

    def cleanup(self, text: str, model: str, system_prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        )
        return response.choices[0].message.content.strip()

    def stream_cleanup(self, text: str, model: str, system_prompt: str) -> Iterator[str]:
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            stream=True,
        )
        for event in response:
            delta = event.choices[0].delta.content or ""
            if delta:
                yield delta

    def process_audio(
        self,
        wav_bytes: bytes,
        model: str,
        prompt: str,
        previous_context: str = "",
        temperature: float = 0.0,
    ) -> MonoResult:
        encoded = base64.b64encode(wav_bytes).decode("ascii")
        response = self.client.chat.completions.create(
            model=model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _mono_user_instruction(previous_context)},
                        {
                            "type": "input_audio",
                            "input_audio": {"data": encoded, "format": "wav"},
                        },
                    ],
                },
            ],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "emit_transcript_result",
                        "description": (
                            "Return the cleaned current-chunk transcript and semantic "
                            "completion confidence."
                        ),
                        "parameters": _MONO_SCHEMA,
                    },
                }
            ],
            tool_choice={
                "type": "function",
                "function": {"name": "emit_transcript_result"},
            },
        )
        message = response.choices[0].message
        tool_calls = message.tool_calls or []
        if not tool_calls:
            raise ValueError("OpenAI mono model did not return emit_transcript_result.")
        arguments = json.loads(tool_calls[0].function.arguments)
        return MonoResult.from_mapping(arguments)


class GeminiProvider:
    def __init__(self, api_key: str):
        from google import genai
        self.client = genai.Client(api_key=api_key)

    @staticmethod
    def _types():
        from google.genai import types
        return types

    def transcribe(self, wav_bytes: bytes, model: str, language: Optional[str] = None) -> str:
        types = self._types()
        language_hint = f" The expected language is {language}." if language else ""
        response = self.client.models.generate_content(
            model=model,
            contents=[
                "Transcribe the speech accurately. Return only the transcript." + language_hint,
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
        )
        return (response.text or "").strip()

    def cleanup(self, text: str, model: str, system_prompt: str) -> str:
        types = self._types()
        response = self.client.models.generate_content(
            model=model,
            contents=text,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        return (response.text or "").strip()

    def stream_cleanup(self, text: str, model: str, system_prompt: str) -> Iterator[str]:
        types = self._types()
        response = self.client.models.generate_content_stream(
            model=model,
            contents=text,
            config=types.GenerateContentConfig(system_instruction=system_prompt),
        )
        for chunk in response:
            delta = chunk.text or ""
            if delta:
                yield delta

    def process_audio(
        self,
        wav_bytes: bytes,
        model: str,
        prompt: str,
        previous_context: str = "",
        temperature: float = 0.0,
    ) -> MonoResult:
        types = self._types()
        response = self.client.models.generate_content(
            model=model,
            contents=[
                _mono_user_instruction(previous_context),
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
            config={
                "system_instruction": prompt,
                "temperature": temperature,
                "response_format": {
                    "text": {
                        "mime_type": "application/json",
                        "schema": _MONO_SCHEMA,
                    }
                },
            },
        )
        return MonoResult.from_mapping(json.loads(response.text or "{}"))
