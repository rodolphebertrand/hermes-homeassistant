"""HTTP client for the Hermes OpenAI-compatible API."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant

from .exceptions import (
    HermesAuthenticationError,
    HermesConnectionError,
    HermesTimeoutError,
)

_LOGGER = logging.getLogger(__name__)


class HermesApiClient:
    """Client for the Hermes OpenAI-compatible API server."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        port: int,
        api_key: str | None,
        timeout: int,
        agent: str | None = None,
        session_idle_minutes: int = 30,
    ) -> None:
        self._hass = hass
        self._base_url = f"http://{host}:{port}"
        self._api_key = api_key
        self._timeout = timeout
        self._agent = (agent or "").strip()
        # "default" (or empty) = no /p/<agent>/ prefix (gateway main profile).
        self._prefix = f"/p/{self._agent}" if self._agent and self._agent != "default" else ""
        # Session continuity: HA conversation_id -> (Hermes session id, last-used epoch).
        self._idle_ttl = max(0, session_idle_minutes) * 60
        self._sessions: dict[str, tuple[str, float]] = {}

    def _pop_session(self, conversation_id: str | None) -> str | None:
        """Valid (not idle-expired) Hermes session id for a HA conversation, if any."""
        if not conversation_id or self._idle_ttl <= 0:
            return None
        entry = self._sessions.get(conversation_id)
        if entry is None:
            return None
        session_id, last_used = entry
        if time.monotonic() - last_used > self._idle_ttl:
            self._sessions.pop(conversation_id, None)
            return None
        return session_id

    def _note_session(self, conversation_id: str | None, session_id: str | None) -> None:
        if conversation_id and session_id:
            self._sessions[conversation_id] = (session_id, time.monotonic())

    @property
    def _api_url(self) -> str:
        return f"{self._base_url}{self._prefix}"

    @property
    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        return headers

    async def health(self) -> bool:
        """Check connectivity. Returns True if healthy."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self._api_url}/health",
                    headers=self._headers,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status == 401:
                        raise HermesAuthenticationError("Invalid API key")
                    return resp.status == 200
        except asyncio.TimeoutError as err:
            raise HermesTimeoutError("Health check timed out") from err
        except HermesAuthenticationError:
            raise
        except Exception as err:
            raise HermesConnectionError(str(err)) from err

    async def chat(
        self,
        message: str,
        conversation_id: str | None = None,
    ) -> str:
        """Send a message and return the assistant's response text."""
        messages = [
            {
                "role": "system",
                "content": (
                    "You are operating as a Home Assistant voice assistant. "
                    "Responses are read aloud by a TTS engine — keep them short, conversational, and spoken-word friendly. "
                    "Never use markdown, bullet lists, code blocks, ASCII art, timeline charts, tables, or any visual formatting. "
                    "Summarize information in plain sentences instead. "
                    "If you need more information to complete a request, always end your response with a direct question. "
                    "For example: 'What time should I set it for?' or 'Which calendar should I add it to?' "
                    "You have access to a physical Awtrix LED clock in the living room. "
                    "When asked to push or show a message on the clock, use the home-assistant skill's awtrix_push command — do not ask which device."
                ),
            },
            {"role": "user", "content": message},
        ]

        payload: dict[str, Any] = {
            "model": "hermes-agent",
            "messages": messages,
            "stream": False,
        }

        # Session continuity: resume the Hermes session bound to this HA
        # conversation (X-Hermes-Session-Id header) instead of starting a
        # brand-new session for every voice question.
        hermes_session_id = self._pop_session(conversation_id)

        request_headers = dict(self._headers)
        if hermes_session_id:
            request_headers["X-Hermes-Session-Id"] = hermes_session_id
        new_session_id: str | None = None

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self._api_url}/v1/chat/completions",
                    headers=request_headers,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=self._timeout),
                ) as resp:
                    if resp.status == 401:
                        raise HermesAuthenticationError("Invalid API key")
                    if resp.status != 200:
                        body = await resp.text()
                        raise HermesConnectionError(f"HTTP {resp.status}: {body}")
                    data = await resp.json()
                    # Track the session the server assigned (first turn) or
                    # confirmed (continuation) so the next turn resumes it.
                    new_session_id = resp.headers.get("X-Hermes-Session-Id")

        except asyncio.TimeoutError as err:
            raise HermesTimeoutError("Request timed out") from err
        except (HermesAuthenticationError, HermesConnectionError):
            raise
        except Exception as err:
            raise HermesConnectionError(str(err)) from err

        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as err:
            raise HermesConnectionError(f"Unexpected response format: {data}") from err
        finally:
            # Remember the session for the next turn of this HA conversation.
            self._note_session(conversation_id, new_session_id)
