"""ILlmProvider: complete(prompt, max_tokens) -> Completion. Temperature 0 and a fixed seed everywhere.

- StandInLocalModel: a deterministic template-based stand-in that follows the same prompt/JSON protocol. It is NOT a
  language model; it lets the whole pipeline (router, guardrails, trace, energy estimate) run and be tested without a
  model runtime. Use OpenAICompatibleProvider with a local runtime (llama.cpp server, vLLM, Ollama /v1) for a real one.
- OpenAICompatibleProvider: HTTP client for any server that offers POST /chat/completions (local or external).
  Not tested against a live server in this project; the transport is injectable for tests.
"""
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

SEED = 42


class ProviderError(Exception):
    """Unavailable, timed out or returned an unusable response."""


@dataclass(frozen=True)
class Completion:
    text: str
    tokens_in: int
    tokens_out: int


class LlmProvider(Protocol):
    name: str
    kind: str                      # "local" or "external"
    def complete(self, prompt: str, max_tokens: int) -> Completion: ...


def count_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)            # rough estimate: about four characters per token


class OpenAICompatibleProvider:
    def __init__(self, base_url: str, model: str, kind: str = "local", api_key: Optional[str] = None, timeout: float = 20.0,
                 transport: Optional[Callable[[str, dict, dict, float], dict]] = None, json_mode: bool = False) -> None:
        self.json_mode = json_mode               # ask the runtime for a JSON object (Ollama /v1 and llama.cpp support response_format)
        self.base_url, self.model, self.kind, self.api_key, self.timeout = base_url.rstrip("/"), model, kind, api_key, timeout
        self.name = f"{kind}:{model}"
        self.transport = transport or self._http

    @staticmethod
    def _http(url: str, body: dict, headers: dict, timeout: float) -> dict:
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json", **headers})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def complete(self, prompt: str, max_tokens: int) -> Completion:
        body = {"model": self.model, "messages": [{"role": "user", "content": prompt}], "temperature": 0, "seed": SEED, "max_tokens": max_tokens}
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            data = self.transport(f"{self.base_url}/chat/completions", body, headers, self.timeout)
            text = data["choices"][0]["message"]["content"]
            usage = data.get("usage") or {}
            return Completion(text, int(usage.get("prompt_tokens", count_tokens(prompt))), int(usage.get("completion_tokens", count_tokens(text))))
        except (OSError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ProviderError(str(exc)) from exc


class ModelByMode:
    """Dynamic model exchange: the local runtime answers with a different model in each operating mode (a larger one
    in GREEN, a smaller and cheaper one in AMBER). RED never reaches a model (the router sends it to the template).
    `mode_reader.current()` is the same cached mode that the rest of the system uses."""
    kind = "local"

    def __init__(self, by_mode: dict[str, "LlmProvider"], mode_reader) -> None:
        self.by_mode, self.mode_reader = by_mode, mode_reader

    def _current(self) -> "LlmProvider":
        mode = self.mode_reader.current()[0]
        return self.by_mode.get(mode) or self.by_mode["GREEN"]

    @property
    def name(self) -> str:
        return self._current().name

    @property
    def available(self) -> bool:
        return bool(getattr(self._current(), "available", True))

    def complete(self, prompt: str, max_tokens: int) -> Completion:
        return self._current().complete(prompt, max_tokens)


_DATA = re.compile(r"<data>(.*?)</data>", re.S)


class StandInLocalModel:
    """Reads the evidence payload from the prompt and phrases it. Deterministic; makes no decision of its own."""
    kind = "local"
    name = "local:stand-in"

    def __init__(self, phraser: Optional[Callable[[dict, str], str]] = None) -> None:
        self.phraser = phraser
        self.available = True

    def complete(self, prompt: str, max_tokens: int) -> Completion:
        if not self.available:
            raise ProviderError("local model runtime unavailable")
        m = _DATA.search(prompt)
        if not m:
            raise ProviderError("no data block in prompt")
        payload = json.loads(m.group(1))
        lang = "sk" if "LANG=sk" in prompt else "en"
        text = (self.phraser or default_phrase)(payload, lang)
        out = json.dumps({"action_label": payload["action"], "explanation": text}, ensure_ascii=False)
        return Completion(out, count_tokens(prompt), count_tokens(out))


def default_phrase(payload: dict, lang: str) -> str:
    from .gateway import template_text          # one place for the wording
    return template_text(payload, lang, simplified=False)
