"""Minimal OpenAI-compatible LLM client."""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from cody_banks.config import ModelConfig


Message = dict[str, str]


class LLMError(RuntimeError):
    """Raised when the configured model endpoint cannot return a chat response."""


@dataclass(frozen=True, slots=True)
class LLMClient:
    config: ModelConfig
    timeout_seconds: float = 120.0

    def chat_completion(self, messages: list[Message]) -> str:
        """Return the assistant message content from a chat completion."""
        response = self.create_chat_completion(messages)
        try:
            content = response["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Model response did not contain choices[0].message.content") from exc

        if not isinstance(content, str):
            raise LLMError("Model response content was not a string")
        return content

    def create_chat_completion(self, messages: list[Message]) -> dict[str, Any]:
        """Call an OpenAI-compatible /chat/completions endpoint."""
        payload = {
            "model": self.config.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        request = Request(
            url=self._chat_completions_url(),
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise LLMError(f"Model endpoint returned HTTP {exc.code}: {details}") from exc
        except URLError as exc:
            raise LLMError(f"Could not reach model endpoint: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError("Timed out waiting for model endpoint") from exc

        try:
            decoded = json.loads(raw_body)
        except json.JSONDecodeError as exc:
            raise LLMError("Model endpoint returned invalid JSON") from exc

        if not isinstance(decoded, dict):
            raise LLMError("Model endpoint returned a non-object JSON response")
        return decoded

    def _chat_completions_url(self) -> str:
        return f"{self.config.base_url.rstrip('/')}/chat/completions"
