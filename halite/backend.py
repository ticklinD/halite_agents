"""
Halite backend — pure agent logic, no TTY.
Communicates with the Ink frontend via JSON-over-stdio.
Run by the Node parent process: node dist/index.js → spawns `python -m halite.backend`.
"""
from __future__ import annotations

import asyncio
import json
import signal
import sys
from typing import Any, Literal

from halite.models.schemas import Message, Session
from halite.config.settings import load_config, AppConfig
from halite.commands.dispatcher import CommandDispatcher
from halite.commands.handlers import register_handlers
from halite.storage.history import HistoryStore
from halite.models.local_provider import OllamaProvider
from halite.models.capability_registry import CapabilityRegistry
from halite.core.classifier import IntentClassifier
from halite.core.router import Router
from halite.tools.base import ToolExecutor
from halite.utils.logging_config import (
    setup_logging, install_exception_hook, logger,
    set_correlation_context,
)

import os
import threading
from pathlib import Path
from uuid import uuid4


class HaliteBackend:
    """Backend agent without a terminal. JSON over stdin/stdout with Node frontend."""

    def __init__(self, debug: bool = False) -> None:
        self.debug_mode = debug
        self.config: AppConfig = load_config()
        setup_logging(debug=self.config.debug_mode or debug)
        install_exception_hook()

        logger.info("Halite backend starting — debug={}", self.debug_mode)

        # Storage
        self.history = HistoryStore()

        # Model state
        self.active_model = ""
        self.active_backend = self.config.default_backend

        # Project root
        self.project_root: Path | None = Path.cwd()
        self.debug_panel = None

        # Session
        self._quit_requested = False
        self._stdin_thread: threading.Thread | None = None
        self.current_session: Session | None = None

        # Router / model layer
        self.ollama = OllamaProvider(host=self.config.ollama_host)
        self.capabilities = CapabilityRegistry()

        # Classifier + router (§6.1) — created before new_session() so
        # new_session can reset stickiness.
        self.classifier = IntentClassifier(self.config)
        self.router = Router(self.config)

        # Task stickiness — once a backend is approved for a task,
        # don't re-classify on every turn (§6.1).
        self._current_task_backend: str | None = None

        self.new_session()

        # Tool executor
        self.executor = ToolExecutor(project_root=self.current_session.project_path)

        # Register all tools
        from halite.tools.registry import ToolRegistry
        ToolRegistry(self.executor)
        from halite.tools.file_tool import set_diff_callback
        from halite.tools.terminal_tool import set_dangerous_callback
        set_diff_callback(self._confirm_diff)
        set_dangerous_callback(self._confirm_dangerous)

        # Command dispatcher
        self.dispatcher = CommandDispatcher()
        register_handlers(self.dispatcher, self)

        # Confirmation gate — Python side: Futures awaiting the Ink reply.
        # Keyed by a UUID string; _read_loop resolves them when
        # confirm_response arrives on stdin.
        self._pending_confirms: dict[str, asyncio.Future[bool]] = {}

        # Detect models
        self._detect_models()

        logger.info(
            "Halite backend initialised — session={}, backend={}",
            self.current_session.id if self.current_session else None,
            self.active_backend,
        )

    # ── Session ─────────────────────────────────────────────────────

    def new_session(self) -> None:
        session = Session(
            id=uuid4(),
            project_path=self.config_project_root(),
            active_model=self.active_model or "",
            backend=self.active_backend,
        )
        self.current_session = session
        self.history.create_session(session)
        # §6.1: reset task stickiness and manual override on new session
        self._current_task_backend = None
        self.router.clear_manual_override()
        set_correlation_context(session_id=str(session.id))
        logger.info("New session created: {}", session.id)

    def config_project_root(self) -> Path | None:
        return Path.cwd()

    def _detect_models(self) -> None:
        if self.config.ollama_default_model:
            self.active_model = self.config.ollama_default_model
        elif self.active_backend == "api":
            self.active_model = "claude-sonnet-4-20250514"
        else:
            self.active_model = ""

    async def _discover_models(self) -> None:
        """Async: query Ollama for installed models."""
        if self.active_backend != "local_ollama":
            return
        try:
            models = await self.ollama.list_models()
        except Exception as exc:
            logger.warning("Model discovery failed: {}", exc)
            return
        if not models:
            return

        names = [m.get("name", "") for m in models]
        logger.info("Installed Ollama models: {}", names)

        preferred = self.config.ollama_default_model
        if preferred and preferred in names:
            pick = preferred
        elif self.config.ollama_classifier_model in names:
            pick = self.config.ollama_classifier_model
        else:
            pick = names[0]

        self.active_model = pick
        logger.info("Active model selected: {}", pick)
        if self.current_session:
            self.current_session.active_model = pick
            self.current_session.backend = self.active_backend

        await self._send({"type": "status_update", "model": pick, "backend": self.active_backend})

    # ── IPC ─────────────────────────────────────────────────────────

    async def _send(self, msg: dict[str, Any]) -> None:
        """Send JSON to the Node frontend."""
        data = json.dumps(msg) + "\n"
        sys.stdout.write(data)
        await asyncio.get_event_loop().run_in_executor(None, sys.stdout.flush)

    async def _read_loop(self) -> None:
        """Read JSON messages from stdin (from Node).

        Uses a dedicated reader thread instead of loop.connect_read_pipe():
        on Windows the ProactorEventLoop crashes with "WinError 6: The handle
        is invalid" / "'_ProactorReadPipeTransport' object has no attribute
        '_empty_waiter'" when the parent process closes the pipe. A plain
        blocking thread works identically on Linux and Windows.
        """
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        self._stdin_thread: threading.Thread | None = None

        def _reader() -> None:
            try:
                while True:
                    raw = sys.stdin.buffer.readline()
                    if not raw:  # EOF — parent closed the pipe
                        break
                    loop.call_soon_threadsafe(
                        queue.put_nowait, raw.decode("utf-8", errors="replace")
                    )
            except Exception:
                pass
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        self._stdin_thread = threading.Thread(target=_reader, name="halite-stdin", daemon=True)
        self._stdin_thread.start()

        buffer = ""
        while True:
            line = await queue.get()
            if line is None:
                break
            buffer += line
            while "\n" in buffer:
                raw, buffer = buffer.split("\n", 1)
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    msg = json.loads(raw)
                    await self._handle_message(msg)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON from frontend: {}", raw[:100])

    async def _handle_message(self, msg: dict) -> None:
        """Handle a message from the Node frontend."""
        msg_type = msg.get("type")

        if msg_type == "ready":
            await self._on_ready()
        elif msg_type == "user_input":
            text = msg.get("text", "").strip()
            if text:
                await self._handle_user_input(text)
        elif msg_type == "quit":
            await self._shutdown()
            self._quit_requested = True
            # Close stdin so the reader thread sees EOF and exits cleanly
            # instead of being torn down mid-readline (avoids the
            # "_enter_buffered_busy" interpreter-shutdown crash).
            try:
                sys.stdin.close()
            except Exception:
                pass
        elif msg_type == "confirm_response":
            confirm_id = msg.get("id", "")
            approved = bool(msg.get("approved", False))
            fut = self._pending_confirms.get(confirm_id)
            if fut is not None and not fut.done():
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(fut.set_result, approved)

    async def _on_ready(self) -> None:
        """Frontend is ready — send welcome + discover models."""
        await self._send({
            "type": "welcome",
            "message": "Welcome to Halite! Type a message to start, or /help for commands.",
        })
        await self._send({"type": "ready"})
        if not self.active_model:
            await self._discover_models()
        await self._send({
            "type": "status_update",
            "model": self.active_model or "none",
            "backend": self.active_backend,
            "session_id": str(self.current_session.id) if self.current_session else None,
            "cwd": str(Path.cwd()),
        })

    # ── Message handling ────────────────────────────────────────────

    async def _handle_user_input(self, text: str) -> None:
        """Process user input from the frontend."""
        turn_id = str(uuid4())[:8]
        set_correlation_context(
            session_id=str(self.current_session.id) if self.current_session else None,
            turn_id=turn_id,
        )

        # Show user message in the frontend
        await self._send({"type": "user_message", "text": text})

        # Check if it's a command
        result = await self.dispatcher.dispatch(text)

        if result.handled:
            logger.debug("Command handled: {}", result.message[:100] if result.message else "")

            if result.action == "quit":
                await self._send({"type": "quit"})
                await self._shutdown()
                sys.exit(0)

            if result.message:
                await self._send({"type": "system_message", "text": result.message})

            self._persist_message("user", text)
            return

        # Not a command — route to model
        self._persist_message("user", text)
        await self._handle_chat_message(text)

    async def _handle_chat_message(self, text: str) -> None:
        """Handle a normal chat message — classify, route, confirm if needed,
        then call the backend. §6.1: task-level stickiness prevents
        re-classifying every turn of an already-approved task."""
        logger.info("Chat message received ({} chars)", len(text))

        # ── §6.1 stickiness: if a backend is already approved for the
        # current task, skip classification and use the same backend.
        if self._current_task_backend is not None:
            logger.info("Task stickiness active — using {}", self._current_task_backend)
            # Still update the active backend to match
            if self._current_task_backend == "api":
                self.active_backend = "api"
            else:
                self.active_backend = "local"
        else:
            # ── Classify the prompt (§6.1: Stage A rules → Stage B SLM)
            decision = self.classifier.classify(text)
            logger.info("Classifier decision: {} (confidence={})", decision.decision, decision.confidence)

            if decision.decision == "clarify":
                # §6.1: on clarify, ask the user — don't route to any backend
                await self._send({
                    "type": "system_message",
                    "text": f"I need more information to proceed. {decision.reasoning}",
                })
                return

            # ── Route through the permission gate (§6.1)
            backend, needs_confirmation = self.router.resolve_backend(decision)
            logger.info("Router: {} (needs_confirmation={})", backend, needs_confirmation)

            if needs_confirmation and backend == "api":
                # §6.1: never silently auto-execute paid API without approval
                approved = await self.request_confirmation("api", {
                    "task_description": text[:200],
                    "reasoning": decision.reasoning,
                })
                if not approved:
                    await self._send({
                        "type": "system_message",
                        "text": "API call declined — staying on local model.",
                    })
                    # Stay on local, don't set stickiness for API
                    backend = "local"

            # Set the active backend and mark task stickiness
            self.active_backend = "api" if backend == "api" else "local"
            self._current_task_backend = backend
            logger.info("Task backend set to '{}' (sticky until session reset)", backend)

        # ── Build messages and call the backend
        history = self.history.get_messages(self.current_session.id)
        messages: list[dict] = []
        for m in history:
            if m.role in ("user", "assistant"):
                messages.append({"role": m.role, "content": m.content})

        await self._route_and_respond(messages)

    async def _route_and_respond(self, messages: list[dict]) -> None:
        """Route to the appropriate backend, get a response, display it."""
        await self._send({"type": "thinking_start", "label": "Generating…"})

        response = ""
        try:
            if self.active_backend == "api":
                from halite.models.api_provider import APIProvider
                from halite.config.secrets import retrieve_secret
                key = retrieve_secret("anthropic_api_key")
                if not key:
                    await self._send({"type": "thinking_stop"})
                    await self._send({
                        "type": "error_message",
                        "text": "No Anthropic API key configured. Use /config to add one, "
                                "or /model to switch to a local model.",
                    })
                    return
                provider = APIProvider(api_key=key, model=self.active_model)
                response = await provider.chat(messages)
                await provider.close()
            else:
                response = await self.ollama.chat(self.active_model, messages)

            await self._send({"type": "thinking_stop"})
            await self._send({"type": "assistant_message", "text": response, "model": self.active_model})
            logger.info("Response received ({} chars)", len(response))

            dog = Message(
                session_id=self.current_session.id,
                role="assistant",
                content=response,
                model_used=self.active_model,
            )
            self.history.add_message(dog)

        except Exception as exc:
            await self._send({"type": "thinking_stop"})
            logger.exception("Failed to get model response: {}", str(exc))
            await self._send({"type": "error_message", "text": f"Failed to get model response: {exc}"})

    # ── Confirmation gate (§6.4 / §7.4) ─────────────────────────────

    async def request_confirmation(
        self,
        kind: str,
        payload: dict[str, Any],
        timeout: float = 60.0,
    ) -> bool:
        """Send a confirm_request to the Ink frontend and block until the
        user answers or *timeout* seconds elapse.  Returns True when
        approved, False otherwise.

        The caller must never return before the user has actually
        answered — the whole point of the gate is to pause the agent.
        """
        confirm_id = str(uuid4())[:12]
        loop = asyncio.get_event_loop()
        fut: asyncio.Future[bool] = loop.create_future()
        self._pending_confirms[confirm_id] = fut

        await self._send({
            "type": "confirm_request",
            "id": confirm_id,
            "kind": kind,
            "payload": payload,
        })

        try:
            approved = await asyncio.wait_for(fut, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("Confirm {} timed out ({}s) — defaulting to denied", confirm_id, timeout)
            approved = False

        self._pending_confirms.pop(confirm_id, None)
        return approved

    # ── Confirmation callbacks (wired to tools) ──────────────────────

    async def _confirm_diff(self, path: Path, old_content: str, new_content: str) -> bool:
        if self.config.trust_level == "auto":
            return True
        return await self.request_confirmation("diff", {
            "path": str(path),
            "old_preview": (old_content[:800] + "...") if len(old_content) > 800 else old_content,
            "new_preview": (new_content[:800] + "...") if len(new_content) > 800 else new_content,
        })

    async def _confirm_dangerous(self, command: str, reason: str) -> bool:
        return await self.request_confirmation("dangerous", {
            "command": command,
            "reason": reason,
        })

    # ── Persistence ─────────────────────────────────────────────────

    def _persist_message(self, role: str, content: str, model_used: str | None = None) -> None:
        if self.current_session is None:
            return
        msg = Message(
            session_id=self.current_session.id,
            role=role,
            content=content,
            model_used=model_used,
        )
        self.history.add_message(msg)

    # ── Lifecycle ───────────────────────────────────────────────────

    async def run(self) -> None:
        """Run the backend until quit."""
        await self._send({"type": "ready"})
        await self._read_loop()

    async def _shutdown(self) -> None:
        logger.info("Halite backend shutting down")
        try:
            await self.ollama.close()
        except Exception:
            pass
        try:
            self.history.close()
        except Exception:
            pass


async def main() -> None:
    # Windows: ensure UTF-8 on stdio so JSON (and non-ASCII text like the
    # "Generating…" label) round-trips correctly regardless of console codepage.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    debug = "--debug" in sys.argv
    backend = HaliteBackend(debug=debug)
    await backend.run()


if __name__ == "__main__":
    asyncio.run(main())