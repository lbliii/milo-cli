"""Session recording — action log writer."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from milo._types import Action


@dataclass(frozen=True, slots=True)
class ActionRecord:
    """Single recorded action with timestamp."""

    timestamp: float
    action: Action
    state_hash: str


@dataclass(frozen=True, slots=True)
class SessionRecording:
    """Complete recorded session."""

    initial_state: Any
    records: tuple[ActionRecord, ...]
    final_state: Any
    metadata: dict[str, str]


def state_hash(state: Any) -> str:
    """SHA256 hash of state repr, truncated to 16 chars."""
    return hashlib.sha256(repr(state).encode()).hexdigest()[:16]


def recording_middleware(
    records: list[dict],
) -> Any:
    """Create a middleware that records actions and state hashes."""

    def middleware(dispatch: Any, get_state: Any) -> Any:
        def recording_dispatch(action: Action) -> None:
            dispatch(action)
            records.append(
                {
                    "timestamp": time.time(),
                    "action_type": action.type,
                    "action_payload": action.payload,
                    "state_hash": state_hash(get_state()),
                }
            )

        return recording_dispatch

    return middleware


def save_recording(
    path: str | Path,
    initial_state: Any,
    records: list[dict],
    final_state: Any,
    metadata: dict[str, str] | None = None,
) -> None:
    """Save a session recording to JSONL."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w") as f:
        # Header
        header = {
            "type": "header",
            "initial_state": repr(initial_state),
            "metadata": metadata or {},
        }
        f.write(json.dumps(header) + "\n")

        # Records
        for record in records:
            record_data = {"type": "action", **record}
            # Convert non-serializable payloads
            if "action_payload" in record_data:
                try:
                    json.dumps(record_data["action_payload"])
                except (TypeError, ValueError):
                    record_data["action_payload"] = repr(record_data["action_payload"])
            f.write(json.dumps(record_data) + "\n")

        # Footer
        footer = {
            "type": "footer",
            "final_state": repr(final_state),
        }
        f.write(json.dumps(footer) + "\n")


def load_recording(path: str | Path) -> SessionRecording:
    """Load a session recording from JSONL."""
    path = Path(path)
    text = path.read_text().strip()
    if not text:
        raise ValueError(f"Empty or invalid recording file: {path}")
    lines = text.split("\n")
    if len(lines) < 2:
        raise ValueError(f"Recording file must have at least a header and footer: {path}")

    header = json.loads(lines[0])
    footer = json.loads(lines[-1])

    records = []
    for line in lines[1:-1]:
        data = json.loads(line)
        if data["type"] == "action":
            records.append(
                ActionRecord(
                    timestamp=data["timestamp"],
                    action=Action(data["action_type"], data.get("action_payload")),
                    state_hash=data["state_hash"],
                )
            )

    return SessionRecording(
        initial_state=header.get("initial_state"),
        records=tuple(records),
        final_state=footer.get("final_state"),
        metadata=header.get("metadata", {}),
    )
