"""Minimal Mistral REST client (embeddings + JSON chat) with retries.

Chat calls use a short retry budget and a cooldown circuit breaker, so a
rate-limited chat endpoint fails over to the extractive path in seconds
instead of minutes. Embedding calls (ingestion) retry more patiently.
"""

import json
import re
import time
from typing import Any

import httpx

from .. import config

_CHAT_COOLDOWN_SECONDS = 120.0
_chat_cooldown_until = 0.0


class MistralError(Exception):
    pass


def _retry_after_seconds(resp: httpx.Response) -> float | None:
    value = resp.headers.get("retry-after")
    if not value:
        return None
    try:
        return max(float(value), 1.0)
    except ValueError:
        return None


def chat_in_cooldown() -> bool:
    return time.time() < _chat_cooldown_until


def _start_chat_cooldown() -> None:
    global _chat_cooldown_until
    _chat_cooldown_until = time.time() + _CHAT_COOLDOWN_SECONDS


class MistralClient:
    def __init__(self, api_key: str | None = None, timeout: float | None = None):
        self.api_key = api_key or config.MISTRAL_API_KEY
        self.timeout = timeout or config.CHAT_TIMEOUT
        if not self.api_key:
            raise MistralError(
                "MISTRAL_API_KEY is not set. Copy backend/.env.example to "
                "backend/.env and add your key."
            )
        self._http = httpx.Client(
            base_url=config.MISTRAL_BASE_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(self.timeout, connect=10.0),
        )

    def close(self) -> None:
        self._http.close()

    def _post(
        self, path: str, payload: dict[str, Any], attempts: int = 4
    ) -> dict[str, Any]:
        last_exc: Exception | None = None
        for attempt in range(attempts):
            try:
                resp = self._http.post(path, json=payload)
                if resp.status_code == 200:
                    return resp.json()
                body = resp.text[:400]
                if resp.status_code in (408, 409, 429, 500, 502, 503, 504):
                    last_exc = MistralError(
                        f"Mistral API {resp.status_code} on {path}: {body}"
                    )
                    retry_after = _retry_after_seconds(resp)
                    backoff = (
                        retry_after
                        if retry_after
                        else min(2.0 * (2**attempt), 30.0)
                    )
                    time.sleep(min(backoff, 30.0))
                    continue
                raise MistralError(f"Mistral API {resp.status_code} on {path}: {body}")
            except httpx.HTTPError as exc:
                last_exc = exc
                time.sleep(min(2.0 * (2**attempt), 30.0))
        raise MistralError(f"Mistral API request failed after retries: {last_exc}")

    def embed(self, texts: list[str], batch_size: int = 8) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            data = self._post(
                "/embeddings",
                {"model": config.MISTRAL_EMBED_MODEL, "input": batch},
                attempts=5,
            )
            items = sorted(data.get("data", []), key=lambda d: d.get("index", 0))
            if len(items) != len(batch):
                raise MistralError(
                    f"Embedding count mismatch: sent {len(batch)}, got {len(items)}"
                )
            vectors.extend([item["embedding"] for item in items])
        return vectors

    def chat_json(self, system: str, user: str, temperature: float = 0.1) -> dict[str, Any]:
        if chat_in_cooldown():
            raise MistralError(
                "Chat API is rate-limited; using extractive mode for now."
            )
        try:
            data = self._post(
                "/chat/completions",
                {
                    "model": config.MISTRAL_CHAT_MODEL,
                    "temperature": temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
                attempts=2,
            )
        except MistralError as exc:
            if "429" in str(exc) or "Rate limit" in str(exc):
                _start_chat_cooldown()
            raise
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise MistralError(f"Unexpected chat response shape: {data}") from exc
        return _parse_json_object(content)


def _parse_json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise MistralError(f"Model did not return JSON: {text[:300]}")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise MistralError(f"Model returned invalid JSON: {text[:300]}") from exc
    if not isinstance(parsed, dict):
        raise MistralError("Model returned JSON that is not an object.")
    return parsed
