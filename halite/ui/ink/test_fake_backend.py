#!/usr/bin/env python3
"""Fake Halite backend for the Ink rendering regression test.

Speaks the same JSON-over-stdio protocol as halite/backend.py but emits a
scripted sequence: startup burst → several chat messages with thinking
toggles → a confirm request → more messages → quit.

Run via HALITE_FAKE_BACKEND (see test_static_rendering.mjs).
"""
import json
import sys
import time


def send(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()
    time.sleep(0.04)


def main() -> None:
    # Startup burst (frontend coalesces these into one frame)
    send({"type": "welcome", "text": "Halite ready"})
    send({"type": "ready"})
    send({"type": "status_update", "model": "qwen3.5:0.8b", "backend": "local",
          "session_id": "abc12345", "cwd": "/tmp"})

    # Several chat messages back to back with thinking toggles
    for i in range(5):
        send({"type": "thinking_start", "label": "Generating..."})
        time.sleep(0.05)
        send({"type": "thinking_stop"})
        send({"type": "assistant_message", "text": f"response {i} " + "x" * 100})
        send({"type": "system_message", "text": f"system note {i}"})

    # A confirm request (the classic corruption trigger)
    send({"type": "confirm_request", "id": "cf1", "kind": "dangerous",
          "payload": {"command": "rm -rf /tmp/x", "reason": "test dangerous cmd"}})
    # Hold it open long enough for the test to answer 'y' (sent ~2s in),
    # then continue the flow so "confirm done" gets rendered.
    time.sleep(3.0)
    send({"type": "system_message", "text": "confirm done"})

    # Quit
    send({"type": "quit"})


if __name__ == "__main__":
    main()