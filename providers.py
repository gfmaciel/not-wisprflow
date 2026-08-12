from __future__ import annotations

import base64
import io
from typing import Iterator, Optional


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

    def process_audio(self, *args, **kwargs) -> str:
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

    def process_audio(self, wav_bytes: bytes, model: str, prompt: str) -> str:
        encoded = base64.b64encode(wav_bytes).decode("ascii")
        response = self.client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Transcribe the supplied audio accurately and apply the system "
                                "cleanup/formatting rules. Return only the final cleaned transcript."
                            ),
                        },
                        {
                            "type": "input_audio",
                            "input_audio": {"data": encoded, "format": "wav"},
                        },
                    ],
                },
            ],
        )
        return response.choices[0].message.content.strip()


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

    def process_audio(self, wav_bytes: bytes, model: str, prompt: str) -> str:
        types = self._types()
        response = self.client.models.generate_content(
            model=model,
            contents=[
                (
                    "Transcribe the supplied audio accurately and apply the system "
                    "cleanup/formatting rules. Return only the final cleaned transcript."
                ),
                types.Part.from_bytes(data=wav_bytes, mime_type="audio/wav"),
            ],
            config=types.GenerateContentConfig(system_instruction=prompt),
        )
        return (response.text or "").strip()
