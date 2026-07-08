"""Waypoint — an agent-native intent journal layered over Git.

Git records what changed. Waypoint records why, which agent made the change,
and which parallel attempt produced it. Journal writes create Git objects and
atomically update only ``refs/waypoint/*``; they never mutate HEAD, the real
index, or the working tree. Only ``pick`` and ``undo`` change working-tree
files, and neither stages those changes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final

from kida import FileSystemLoader

from milo import (
    CLI,
    Action,
    Context,
    Ge,
    Le,
    MaxLen,
    MCPAppResourceMeta,
    MCPAppToolMeta,
    MinLen,
    Option,
    Pattern,
    Positional,
    Quit,
    SpecialKey,
)
from milo.streaming import Progress
from milo.templates import get_env

_ID_EXPRESSION: Final = r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?"
_ID_PATTERN: Final = re.compile(_ID_EXPRESSION)
_OID_PATTERN: Final = re.compile(r"[0-9a-f]{7,64}")
_HUNK_PATTERN: Final = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_TRAILER_PREFIX: Final = "Waypoint-"
_META_REF_NAME: Final = "meta"
_DEFAULT_TIMEOUT: Final = 10.0
_AUTO_INPUT_LIMIT: Final = 1_000_000
_TEMPLATE_DIR: Final = Path(__file__).parent / "templates"
_AGENT_ENV_KEYS: Final = (
    "WAYPOINT_AGENT",
    "CONDUCTOR_AGENT_ID",
    "CLAUDE_AGENT_ID",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_SESSION_ID",
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
    "GITHUB_ACTOR",
    "USER",
)
REF_NAMESPACE: Final = "refs/waypoint"

Identifier = Annotated[
    str,
    MinLen(1),
    MaxLen(64),
    Pattern(f"^{_ID_EXPRESSION}$"),
]
Title = Annotated[str, Positional("TITLE"), MinLen(1), MaxLen(200)]
TaskReference = Annotated[str, MinLen(1), MaxLen(200)]
Why = Annotated[str, MinLen(1), MaxLen(500)]
IntentArgument = Annotated[
    str,
    Positional("INTENT"),
    MinLen(1),
    MaxLen(64),
    Pattern(f"^{_ID_EXPRESSION}$"),
]
IntentOption = Annotated[
    str,
    MinLen(1),
    MaxLen(64),
    Pattern(f"^{_ID_EXPRESSION}$"),
    Option(aliases=("--intent",), metavar="ID"),
]
AttemptArgument = Annotated[
    str,
    Positional("ATTEMPT"),
    MinLen(1),
    MaxLen(129),
    Pattern(f"^{_ID_EXPRESSION}(?:/{_ID_EXPRESSION})?$"),
]
CheckpointArgument = Annotated[
    str,
    Positional("CHECKPOINT"),
    MinLen(7),
    MaxLen(64),
    Pattern(r"^[0-9a-f]{7,64}$"),
]
TargetArgument = Annotated[str, Positional("PATH[:LINE]"), MinLen(1), MaxLen(500)]


class WaypointError(RuntimeError):
    """An actionable repository or journal failure."""


@dataclass(frozen=True, slots=True)
class GitResult:
    """Captured result from one bounded Git subprocess."""

    returncode: int
    stdout: str
    stderr: str


def _run_git_process(
    git: str,
    args: tuple[str, ...],
    *,
    cwd: Path,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float = _DEFAULT_TIMEOUT,
) -> GitResult:
    """Run Git with captured streams and an explicit timeout."""
    process_env = os.environ.copy()
    if env:
        process_env.update(env)
    try:
        completed = subprocess.run(
            (git, *args),
            cwd=cwd,
            env=process_env,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as error:
        raise WaypointError(
            f"Git timed out after {timeout:g}s while running: git {' '.join(args)}"
        ) from error
    except OSError as error:
        raise WaypointError(f"Could not run Git: {error}") from error
    return GitResult(
        returncode=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def _git_failure(args: tuple[str, ...], result: GitResult) -> WaypointError:
    detail = result.stderr.strip() or result.stdout.strip() or "no diagnostic output"
    return WaypointError(f"git {' '.join(args)} failed: {detail}")


def validate_id(value: str, *, field: str) -> str:
    """Validate an identifier used inside the Waypoint Git ref namespace.

    Args:
        value: Candidate lowercase, hyphenated identifier.
        field: Human-readable field name used in the repair message.
    """
    if not _ID_PATTERN.fullmatch(value):
        raise ValueError(
            f"{field} must be 1-64 lowercase letters, digits, or hyphens; "
            "it cannot start or end with a hyphen"
        )
    return value


def _single_line(value: str, *, field: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field} must not be blank")
    if "\n" in normalized or "\r" in normalized:
        raise ValueError(f"{field} must be a single line")
    return normalized


def _timestamp_text(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Waypoint timestamp must be timezone-aware")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("Waypoint-Timestamp must be an ISO 8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Waypoint-Timestamp must include a timezone")
    return parsed


def _render_trailers(values: dict[str, str]) -> str:
    return "\n".join(f"{_TRAILER_PREFIX}{name}: {value}" for name, value in sorted(values.items()))


def _parse_trailers(message: str) -> dict[str, str]:
    trailers: dict[str, str] = {}
    for line in message.splitlines()[1:]:
        if not line.startswith(_TRAILER_PREFIX):
            continue
        key, separator, value = line.removeprefix(_TRAILER_PREFIX).partition(": ")
        if not separator or not key or not value:
            raise ValueError(f"malformed Waypoint trailer: {line!r}")
        if key in trailers:
            raise ValueError(f"duplicate Waypoint trailer: {key}")
        trailers[key] = value
    return trailers


def _require_trailers(trailers: dict[str, str], required: set[str]) -> None:
    missing = sorted(required - trailers.keys())
    if missing:
        raise ValueError(f"missing Waypoint trailer(s): {', '.join(missing)}")


def waypoint_ref(intent_id: str, attempt_id: str) -> str:
    """Return the validated ref for an attempt's latest checkpoint."""
    intent = validate_id(intent_id, field="intent id")
    attempt = validate_id(attempt_id, field="attempt id")
    if attempt == _META_REF_NAME:
        raise ValueError(f"attempt id {_META_REF_NAME!r} is reserved for intent metadata")
    return f"{REF_NAMESPACE}/{intent}/{attempt}"


def _intent_ref(intent_id: str) -> str:
    intent = validate_id(intent_id, field="intent id")
    return f"{REF_NAMESPACE}/{intent}/{_META_REF_NAME}"


@dataclass(frozen=True, slots=True)
class Intent:
    """A stated goal that one or more agents may attempt."""

    id: str
    title: str
    agent: str
    created_at: datetime
    task_ref: str | None = None

    def __post_init__(self) -> None:
        validate_id(self.id, field="intent id")
        validate_id(self.agent, field="agent id")
        _single_line(self.title, field="intent title")
        _timestamp_text(self.created_at)
        if self.task_ref is not None:
            _single_line(self.task_ref, field="task reference")

    def commit_message(self) -> str:
        """Render deterministic commit text for the intent metadata ref."""
        trailers = {
            "Agent": self.agent,
            "Intent": self.id,
            "Timestamp": _timestamp_text(self.created_at),
            "Type": "intent",
        }
        if self.task_ref is not None:
            trailers["Task"] = self.task_ref
        return f"waypoint-intent: {self.title}\n\n{_render_trailers(trailers)}\n"


def parse_intent_message(message: str) -> Intent:
    """Parse an intent from its metadata commit message."""
    lines = message.splitlines()
    if not lines or not lines[0].startswith("waypoint-intent: "):
        raise ValueError("intent message must start with 'waypoint-intent: '")
    trailers = _parse_trailers(message)
    _require_trailers(trailers, {"Agent", "Intent", "Timestamp", "Type"})
    if trailers["Type"] != "intent":
        raise ValueError("Waypoint-Type must be 'intent' for intent metadata")
    return Intent(
        id=trailers["Intent"],
        title=lines[0].removeprefix("waypoint-intent: "),
        agent=trailers["Agent"],
        created_at=_parse_timestamp(trailers["Timestamp"]),
        task_ref=trailers.get("Task"),
    )


@dataclass(frozen=True, slots=True)
class CheckpointMetadata:
    """Metadata encoded in a checkpoint commit's trailers."""

    intent_id: str
    attempt_id: str
    agent: str
    why: str
    created_at: datetime
    task_ref: str | None = None

    def __post_init__(self) -> None:
        validate_id(self.intent_id, field="intent id")
        validate_id(self.attempt_id, field="attempt id")
        if self.attempt_id == _META_REF_NAME:
            raise ValueError(f"attempt id {_META_REF_NAME!r} is reserved for intent metadata")
        validate_id(self.agent, field="agent id")
        _single_line(self.why, field="checkpoint why")
        _timestamp_text(self.created_at)
        if self.task_ref is not None:
            _single_line(self.task_ref, field="task reference")

    def commit_message(self) -> str:
        """Render deterministic Git commit text with Waypoint trailers."""
        trailers = {
            "Agent": self.agent,
            "Attempt": self.attempt_id,
            "Intent": self.intent_id,
            "Timestamp": _timestamp_text(self.created_at),
            "Type": "checkpoint",
        }
        if self.task_ref is not None:
            trailers["Task"] = self.task_ref
        return f"waypoint: {self.why}\n\n{_render_trailers(trailers)}\n"


def parse_checkpoint_message(message: str) -> CheckpointMetadata:
    """Parse Waypoint metadata from a checkpoint commit message."""
    lines = message.splitlines()
    if not lines or not lines[0].startswith("waypoint: "):
        raise ValueError("checkpoint message must start with 'waypoint: '")
    trailers = _parse_trailers(message)
    _require_trailers(trailers, {"Agent", "Attempt", "Intent", "Timestamp", "Type"})
    if trailers["Type"] != "checkpoint":
        raise ValueError("Waypoint-Type must be 'checkpoint' for checkpoint metadata")
    return CheckpointMetadata(
        intent_id=trailers["Intent"],
        attempt_id=trailers["Attempt"],
        agent=trailers["Agent"],
        why=lines[0].removeprefix("waypoint: "),
        created_at=_parse_timestamp(trailers["Timestamp"]),
        task_ref=trailers.get("Task"),
    )


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """One checkpoint commit and its immediate parent."""

    oid: str
    parent_oid: str
    metadata: CheckpointMetadata


@dataclass(frozen=True, slots=True)
class TimelineRow:
    """One display-ready checkpoint row in the interactive timeline."""

    group: str
    show_group: bool
    checkpoint: str
    created_at: str
    agent: str
    why: str
    diffstat: str


@dataclass(frozen=True, slots=True)
class TimelineState:
    """Pure navigation state for the Waypoint timeline."""

    rows: tuple[TimelineRow, ...]
    selected: int = 0
    expanded: bool = False

    @property
    def selected_row(self) -> TimelineRow | None:
        if not self.rows:
            return None
        return self.rows[self.selected]


def timeline_reducer(state: TimelineState | None, action: Action) -> TimelineState | Quit:
    """Navigate with j/k or arrows, expand with Enter, and quit with q/Escape."""
    if state is None:
        return TimelineState(rows=())
    if action.type != "@@KEY":
        return state
    key = action.payload
    if key.name == SpecialKey.ESCAPE or key.char == "q":
        return Quit(state)
    if not state.rows:
        return state
    if key.name == SpecialKey.DOWN or key.char == "j":
        return replace(
            state,
            selected=min(len(state.rows) - 1, state.selected + 1),
            expanded=False,
        )
    if key.name == SpecialKey.UP or key.char == "k":
        return replace(state, selected=max(0, state.selected - 1), expanded=False)
    if key.name == SpecialKey.ENTER:
        return replace(state, expanded=not state.expanded)
    return state


@dataclass(frozen=True, slots=True)
class GitRepository:
    """Bounded Git plumbing for one repository."""

    root: Path
    git: str
    timeout: float = _DEFAULT_TIMEOUT

    @classmethod
    def discover(cls, start: Path | None = None) -> GitRepository:
        """Locate the containing Git repository without changing process cwd."""
        git = shutil.which("git")
        if git is None:
            raise WaypointError("Git is required; install git and retry")
        location = (start or Path.cwd()).resolve()
        result = _run_git_process(
            git,
            ("-C", str(location), "rev-parse", "--show-toplevel"),
            cwd=location,
        )
        if result.returncode != 0:
            raise WaypointError(
                "Waypoint must run inside a Git repository; run `git init` or change directory"
            )
        return cls(root=Path(result.stdout.strip()).resolve(), git=git)

    def run(
        self,
        *args: str,
        input_text: str | None = None,
        env: dict[str, str] | None = None,
        check: bool = True,
    ) -> GitResult:
        """Run one Git command rooted at this repository."""
        result = _run_git_process(
            self.git,
            tuple(args),
            cwd=self.root,
            input_text=input_text,
            env=env,
            timeout=self.timeout,
        )
        if check and result.returncode != 0:
            raise _git_failure(tuple(args), result)
        return result

    def head(self) -> str:
        """Return HEAD or explain that an initial commit is required."""
        result = self.run("rev-parse", "--verify", "HEAD", check=False)
        if result.returncode != 0:
            raise WaypointError("Waypoint requires an initial Git commit before journaling")
        return result.stdout.strip()

    def ref_oid(self, ref: str) -> str | None:
        """Resolve a full ref without accepting revision expressions."""
        result = self.run("rev-parse", "--verify", "--quiet", ref, check=False)
        if result.returncode == 1:
            return None
        if result.returncode != 0:
            raise _git_failure(("rev-parse", "--verify", "--quiet", ref), result)
        return result.stdout.strip()

    def _zero_oid(self) -> str:
        object_format = self.run("rev-parse", "--show-object-format").stdout.strip()
        lengths = {"sha1": 40, "sha256": 64}
        try:
            return "0" * lengths[object_format]
        except KeyError as error:
            raise WaypointError(f"Unsupported Git object format: {object_format!r}") from error

    def update_ref(self, ref: str, new_oid: str, old_oid: str | None) -> None:
        """Compare-and-swap one Waypoint ref for free-threading safety."""
        expected = old_oid or self._zero_oid()
        result = self.run("update-ref", ref, new_oid, expected, check=False)
        if result.returncode != 0:
            raise WaypointError(
                f"Waypoint ref {ref!r} changed concurrently; inspect the latest attempt and retry"
            )

    def snapshot_tree(self) -> str:
        """Write the current worktree to a tree through an isolated index."""
        head = self.head()
        with tempfile.TemporaryDirectory(prefix="waypoint-index-") as directory:
            index = str(Path(directory) / "index")
            env = {"GIT_INDEX_FILE": index}
            self.run("read-tree", head, env=env)
            self.run("add", "-A", "--", ".", env=env)
            return self.run("write-tree", env=env).stdout.strip()

    def commit_tree(
        self,
        tree_oid: str,
        message: str,
        *,
        parent_oid: str,
        agent: str,
        created_at: datetime,
    ) -> str:
        """Create one deterministic commit object without moving HEAD."""
        timestamp = _timestamp_text(created_at)
        env = {
            "GIT_AUTHOR_NAME": agent,
            "GIT_AUTHOR_EMAIL": "waypoint@local",
            "GIT_AUTHOR_DATE": timestamp,
            "GIT_COMMITTER_NAME": agent,
            "GIT_COMMITTER_EMAIL": "waypoint@local",
            "GIT_COMMITTER_DATE": timestamp,
        }
        return self.run(
            "commit-tree",
            tree_oid,
            "-p",
            parent_oid,
            input_text=message,
            env=env,
        ).stdout.strip()

    def commit_message(self, oid: str) -> str:
        return self.run("show", "-s", "--format=%B", oid).stdout

    def parent_oid(self, oid: str) -> str:
        record = self.run("rev-list", "--parents", "-n", "1", oid).stdout.split()
        if len(record) < 2:
            raise WaypointError(f"Checkpoint {oid[:12]} has no parent commit")
        return record[1]

    def tree_oid(self, oid: str) -> str:
        return self.run("rev-parse", f"{oid}^{{tree}}").stdout.strip()

    def refs(self) -> list[tuple[str, str, str]]:
        """Return ``(intent, final component, oid)`` for valid Waypoint refs."""
        output = self.run(
            "for-each-ref",
            "--format=%(refname) %(objectname)",
            f"{REF_NAMESPACE}/",
        ).stdout
        records: list[tuple[str, str, str]] = []
        prefix = f"{REF_NAMESPACE}/"
        for line in output.splitlines():
            ref, separator, oid = line.partition(" ")
            if not separator or not ref.startswith(prefix):
                continue
            parts = ref.removeprefix(prefix).split("/")
            if len(parts) != 2:
                continue
            intent_id, name = parts
            if _ID_PATTERN.fullmatch(intent_id) and _ID_PATTERN.fullmatch(name):
                records.append((intent_id, name, oid))
        return records

    def read_intent(self, intent_id: str) -> Intent:
        ref = _intent_ref(intent_id)
        oid = self.ref_oid(ref)
        if oid is None:
            raise WaypointError(
                f"Unknown intent {intent_id!r}; run `wp intents` or create it with `wp intent`"
            )
        try:
            return parse_intent_message(self.commit_message(oid))
        except ValueError as error:
            raise WaypointError(f"Intent metadata at {ref!r} is invalid: {error}") from error

    def list_intents(self) -> list[Intent]:
        intents: list[Intent] = []
        for intent_id, name, oid in self.refs():
            if name != _META_REF_NAME:
                continue
            try:
                parsed = parse_intent_message(self.commit_message(oid))
            except ValueError as error:
                raise WaypointError(
                    f"Intent metadata for {intent_id!r} is invalid: {error}"
                ) from error
            intents.append(parsed)
        return sorted(intents, key=lambda item: (item.created_at, item.id))

    def attempt_refs(self, intent_id: str | None = None) -> list[tuple[str, str, str]]:
        if intent_id is not None:
            validate_id(intent_id, field="intent id")
        return [
            record
            for record in self.refs()
            if record[1] != _META_REF_NAME and (intent_id is None or record[0] == intent_id)
        ]

    def checkpoint_history(self, intent_id: str, attempt_id: str, oid: str) -> list[Checkpoint]:
        """Return newest-to-oldest checkpoints for one attempt ref."""
        history: list[Checkpoint] = []
        current = oid
        while True:
            try:
                metadata = parse_checkpoint_message(self.commit_message(current))
            except ValueError:
                break
            if metadata.intent_id != intent_id or metadata.attempt_id != attempt_id:
                break
            parent = self.parent_oid(current)
            history.append(Checkpoint(oid=current, parent_oid=parent, metadata=metadata))
            current = parent
        if not history:
            raise WaypointError(
                f"Attempt ref {waypoint_ref(intent_id, attempt_id)!r} has no valid checkpoints"
            )
        return history

    def all_checkpoints(self) -> list[Checkpoint]:
        checkpoints: dict[str, Checkpoint] = {}
        for intent_id, attempt_id, oid in self.attempt_refs():
            for checkpoint in self.checkpoint_history(intent_id, attempt_id, oid):
                checkpoints[checkpoint.oid] = checkpoint
        return sorted(
            checkpoints.values(),
            key=lambda item: (item.metadata.created_at, item.oid),
            reverse=True,
        )

    def resolve_attempt(self, value: str) -> tuple[str, str, str]:
        """Resolve ``attempt`` or ``intent/attempt`` to one ref."""
        if "/" in value:
            intent_id, separator, attempt_id = value.partition("/")
            if not separator or "/" in attempt_id:
                raise WaypointError("Attempt must be ATTEMPT or INTENT/ATTEMPT")
            ref = waypoint_ref(intent_id, attempt_id)
            oid = self.ref_oid(ref)
            if oid is None:
                raise WaypointError(f"Unknown attempt {value!r}; run `wp attempts {intent_id}`")
            return intent_id, attempt_id, oid

        attempt_id = validate_id(value, field="attempt id")
        matches = [record for record in self.attempt_refs() if record[1] == attempt_id]
        if not matches:
            raise WaypointError(f"Unknown attempt {attempt_id!r}; run `wp intents` first")
        if len(matches) > 1:
            choices = ", ".join(f"{intent}/{attempt}" for intent, attempt, _ in matches)
            raise WaypointError(
                f"Attempt {attempt_id!r} is ambiguous; use INTENT/ATTEMPT ({choices})"
            )
        return matches[0]

    def resolve_checkpoint(self, prefix: str) -> Checkpoint:
        if not _OID_PATTERN.fullmatch(prefix):
            raise WaypointError("Checkpoint must be a 7-64 character lowercase hexadecimal id")
        matches = [item for item in self.all_checkpoints() if item.oid.startswith(prefix)]
        if not matches:
            raise WaypointError(f"Unknown Waypoint checkpoint {prefix!r}")
        if len(matches) > 1:
            raise WaypointError(
                f"Checkpoint prefix {prefix!r} is ambiguous; provide more characters"
            )
        return matches[0]

    def changed_paths(self, old_oid: str, new_oid: str) -> list[str]:
        output = self.run(
            "diff",
            "--name-only",
            "-z",
            "--no-renames",
            old_oid,
            new_oid,
        ).stdout
        return [path for path in output.split("\0") if path]

    def apply_attempt(self, base_oid: str, checkpoint_oid: str, *, force: bool) -> list[str]:
        """Apply an attempt delta to the working tree without touching the index."""
        paths = self.changed_paths(base_oid, checkpoint_oid)
        if not paths:
            return []
        if force:
            self.run("restore", f"--source={checkpoint_oid}", "--worktree", "--", *paths)
            return paths

        patch = self.run(
            "diff",
            "--binary",
            "--full-index",
            "--no-renames",
            base_oid,
            checkpoint_oid,
        ).stdout
        check = self.run(
            "apply",
            "--check",
            "--whitespace=nowarn",
            "-",
            input_text=patch,
            check=False,
        )
        if check.returncode != 0:
            raise WaypointError(
                "Attempt conflicts with the current working tree; resolve local changes or rerun "
                "with `--force` to overwrite only the attempt's changed paths"
            )
        self.run("apply", "--whitespace=nowarn", "-", input_text=patch)
        return paths

    def reverse_checkpoint(self, checkpoint: Checkpoint) -> list[str]:
        """Reverse one checkpoint delta in the working tree only."""
        paths = self.changed_paths(checkpoint.parent_oid, checkpoint.oid)
        patch = self.run(
            "diff",
            "--binary",
            "--full-index",
            "--no-renames",
            checkpoint.parent_oid,
            checkpoint.oid,
        ).stdout
        check = self.run(
            "apply",
            "--reverse",
            "--check",
            "--whitespace=nowarn",
            "-",
            input_text=patch,
            check=False,
        )
        if check.returncode != 0:
            raise WaypointError(
                "Checkpoint cannot be undone cleanly against the current working tree; "
                "restore the checkpoint's affected lines and retry"
            )
        self.run(
            "apply",
            "--reverse",
            "--whitespace=nowarn",
            "-",
            input_text=patch,
        )
        return paths

    def checkpoint_touches(self, checkpoint: Checkpoint, path: str, line: int | None) -> bool:
        """Return whether one checkpoint changes a path or zero-context line range."""
        diff = self.run(
            "diff",
            "--unified=0",
            "--no-ext-diff",
            "--no-renames",
            checkpoint.parent_oid,
            checkpoint.oid,
            "--",
            path,
        ).stdout
        if not diff:
            return False
        if line is None:
            return True
        for record in diff.splitlines():
            match = _HUNK_PATTERN.match(record)
            if match is None:
                continue
            old_start, old_count, new_start, new_count = (
                int(match.group(1)),
                int(match.group(2) or "1"),
                int(match.group(3)),
                int(match.group(4) or "1"),
            )
            old_touched = old_count > 0 and old_start <= line < old_start + old_count
            new_touched = new_count > 0 and new_start <= line < new_start + new_count
            if old_touched or new_touched:
                return True
        return False


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "intent")[:64].rstrip("-")


def _payload_text(payload: dict[str, object], *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _resolve_agent(explicit: str | None, payload: dict[str, object] | None = None) -> str:
    """Resolve agent identity from an override, hook payload, or environment."""
    if explicit is not None:
        return validate_id(explicit, field="agent id")
    if payload is not None:
        payload_agent = _payload_text(payload, "agent_id", "agent", "session_id")
        if payload_agent is not None:
            return validate_id(_slugify(payload_agent), field="agent id")
    for key in _AGENT_ENV_KEYS:
        value = os.environ.get(key)
        if value:
            return validate_id(_slugify(value), field="agent id")
    return "unknown-agent"


def _read_auto_payload() -> dict[str, object]:
    """Read one bounded hook payload without blocking an interactive terminal."""
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read(_AUTO_INPUT_LIMIT + 1)
    if len(raw) > _AUTO_INPUT_LIMIT:
        raise WaypointError("Automatic checkpoint input exceeds the 1 MB safety limit")
    if not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"summary": raw.strip()}
    if not isinstance(parsed, dict):
        raise WaypointError("Automatic checkpoint input must be a JSON object or plain text")
    return parsed


def _auto_why(payload: dict[str, object]) -> str:
    explicit = os.environ.get("WAYPOINT_WHY") or _payload_text(
        payload,
        "why",
        "summary",
        "turn_summary",
        "last_assistant_message",
    )
    if explicit:
        return _single_line(explicit[:500], field="checkpoint why")
    tool_name = _payload_text(payload, "tool_name")
    if tool_name:
        tool_input = payload.get("tool_input")
        detail = ""
        if tool_input is not None:
            detail = json.dumps(tool_input, sort_keys=True, separators=(",", ":"), default=str)
        text = f"{tool_name}: {detail}" if detail else f"completed {tool_name}"
        return _single_line(text[:500], field="checkpoint why")
    event = _payload_text(payload, "hook_event_name") or "agent turn"
    return f"automatic checkpoint after {event}"[:500]


def _auto_intent(payload: dict[str, object]) -> tuple[str, str, str | None]:
    intent_source = os.environ.get("WAYPOINT_INTENT") or _payload_text(
        payload, "intent_id", "task_id", "session_id"
    )
    if intent_source is None:
        raise WaypointError(
            "Automatic checkpoint could not infer an intent; set WAYPOINT_INTENT or provide "
            "intent_id, task_id, or session_id in the hook payload"
        )
    intent_id = validate_id(_slugify(intent_source), field="intent id")
    title = os.environ.get("WAYPOINT_TASK") or _payload_text(
        payload, "task", "task_description", "prompt"
    )
    task_ref = os.environ.get("WAYPOINT_TASK_REF") or _payload_text(payload, "task_id")
    return intent_id, (title or f"Agent session {intent_source}")[:200], task_ref


def _journal_events(repo: GitRepository) -> list[dict]:
    """Return immutable intent/checkpoint events in append order."""
    events: list[tuple[datetime, dict]] = []
    for _intent_id, name, oid in repo.refs():
        if name != _META_REF_NAME:
            continue
        intent_value = parse_intent_message(repo.commit_message(oid))
        events.append(
            (
                intent_value.created_at,
                {
                    "type": "intent",
                    **_intent_payload(intent_value),
                    "commit": oid,
                },
            )
        )
    for checkpoint in repo.all_checkpoints():
        metadata = checkpoint.metadata
        diffstat = (
            repo.run("diff", "--stat", "--format=", checkpoint.parent_oid, checkpoint.oid)
            .stdout.strip()
            .replace("\n", " · ")
        )
        events.append(
            (
                metadata.created_at,
                {
                    "type": "checkpoint",
                    "intent": metadata.intent_id,
                    "attempt": metadata.attempt_id,
                    "checkpoint": checkpoint.oid,
                    "parent": checkpoint.parent_oid,
                    "agent": metadata.agent,
                    "why": metadata.why,
                    "diffstat": diffstat,
                    "task_ref": metadata.task_ref,
                    "created_at": _timestamp_text(metadata.created_at),
                },
            )
        )
    return [event for _, event in sorted(events, key=lambda item: (item[0], str(item[1])))]


def _timeline_rows(repo: GitRepository) -> tuple[TimelineRow, ...]:
    checkpoint_events = [event for event in _journal_events(repo) if event["type"] == "checkpoint"]
    checkpoint_events.sort(
        key=lambda event: (str(event["intent"]), str(event["attempt"]), str(event["created_at"]))
    )
    rows: list[TimelineRow] = []
    previous_group = ""
    for event in checkpoint_events:
        group = f"{event['intent']} / {event['attempt']}"
        rows.append(
            TimelineRow(
                group=group,
                show_group=group != previous_group,
                checkpoint=str(event["checkpoint"])[:12],
                created_at=str(event["created_at"]),
                agent=str(event["agent"]),
                why=str(event["why"]),
                diffstat=str(event["diffstat"]).replace("\n", " · ") or "no diffstat",
            )
        )
        previous_group = group
    return tuple(rows)


def _timeline_env():
    return get_env(loader=FileSystemLoader(str(_TEMPLATE_DIR)))


def _render_intents_plain(result: list[dict], _ctx: Context) -> str:
    if not result:
        return 'No intents yet. Start with: wp intent "Describe the goal"'
    lines = [f"INTENTS  {len(result)}"]
    for item in result:
        task = f"  [{item['task_ref']}]" if item.get("task_ref") else ""
        lines.append(f"  {item['id']:<20} {item['title']}  @{item['agent']}{task}")
    lines.append(f"Next: wp attempts {result[0]['id']}")
    return "\n".join(lines)


def _render_attempts_plain(result: list[dict], _ctx: Context) -> str:
    if not result:
        return "No attempts yet. Edit files, then run wp checkpoint."
    lines = [f"ATTEMPTS  {result[0]['intent']}  ({len(result)} competing)"]
    for item in result:
        lines.append(
            f"  {item['attempt']:<20} {item['checkpoints']} checkpoint(s)  "
            f"{str(item['checkpoint'])[:12]}  {item['why']}"
        )
        if item.get("diffstat"):
            lines.append(f"    {str(item['diffstat']).replace(chr(10), ' · ')}")
    lines.append(f"Pick: wp pick {result[0]['intent']}/<attempt>")
    return "\n".join(lines)


def _render_log_plain(result: list[dict], ctx: Context) -> str:
    if ctx.is_interactive:
        return ""
    checkpoints = [event for event in result if event["type"] == "checkpoint"]
    if not checkpoints:
        return "No checkpoints yet. Edit files, then run wp checkpoint."
    lines = [f"WAYPOINT TIMELINE  {len(checkpoints)} checkpoint(s)"]
    previous_group = ""
    for event in checkpoints:
        group = f"{event['intent']} / {event['attempt']}"
        if group != previous_group:
            lines.append(f"\n{group}")
            previous_group = group
        lines.append(
            f"  {str(event['checkpoint'])[:12]}  {event['created_at']}  "
            f"@{event['agent']}  {event['why']}"
        )
        if event.get("diffstat"):
            lines.append(f"    {str(event['diffstat']).replace(chr(10), ' · ')}")
    lines.append("\nUse --format table or --format json for non-interactive consumers.")
    return "\n".join(lines)


def _intent_payload(intent_value: Intent) -> dict[str, str | None]:
    return {
        "id": intent_value.id,
        "title": intent_value.title,
        "agent": intent_value.agent,
        "task_ref": intent_value.task_ref,
        "created_at": _timestamp_text(intent_value.created_at),
    }


def _parse_target(repo: GitRepository, target: str) -> tuple[str, int | None]:
    path_text, separator, line_text = target.rpartition(":")
    if separator and line_text.isdigit():
        path_value = path_text
        line = int(line_text)
        if line < 1:
            raise ValueError("line number must be at least 1")
    else:
        path_value = target
        line = None
    if not path_value:
        raise ValueError("path must not be blank")
    candidate = (repo.root / path_value).resolve()
    if not candidate.is_relative_to(repo.root):
        raise ValueError("path must stay inside the Git repository")
    return candidate.relative_to(repo.root).as_posix(), line


cli = CLI(
    name="wp",
    description=(
        "Declare an intent, checkpoint competing attempts, compare them, pick a winner, "
        "and explain why each change exists."
    ),
    version="0.1.0",
)


@cli.command(
    "about", description="Describe the Waypoint showcase", annotations={"readOnlyHint": True}
)
def about() -> dict[str, str]:
    """Describe Waypoint and its Git ownership boundary."""
    return {
        "name": "Waypoint",
        "purpose": "An agent-native intent journal layered over Git.",
        "ref_namespace": REF_NAMESPACE,
        "write_boundary": "journal refs and objects; pick/undo change only the working tree",
    }


@cli.command("intent", description="Declare a new intent")
def create_intent(
    title: Title,
    intent_id: Identifier | None = None,
    agent: Identifier | None = None,
    task_ref: TaskReference | None = None,
) -> dict[str, str | None]:
    """Declare a goal that one or more agents may attempt.

    Args:
        title: Human-readable goal.
        intent_id: Stable id; defaults to a unique slug of the title.
        agent: Agent or person declaring the intent.
        task_ref: Optional external issue or task reference.
    """
    repo = GitRepository.discover()
    resolved_agent = _resolve_agent(agent)
    parent = repo.head()
    existing = {item.id for item in repo.list_intents()}
    if intent_id is None:
        base = _slugify(title)
        candidate = base
        suffix = 2
        while candidate in existing:
            ending = f"-{suffix}"
            candidate = f"{base[: 64 - len(ending)].rstrip('-')}{ending}"
            suffix += 1
        intent_id = candidate
    else:
        validate_id(intent_id, field="intent id")
        if intent_id in existing:
            raise WaypointError(f"Intent {intent_id!r} already exists; choose another id")

    created_at = datetime.now(UTC)
    intent_value = Intent(
        id=intent_id,
        title=title,
        agent=resolved_agent,
        task_ref=task_ref,
        created_at=created_at,
    )
    oid = repo.commit_tree(
        repo.tree_oid(parent),
        intent_value.commit_message(),
        parent_oid=parent,
        agent=resolved_agent,
        created_at=created_at,
    )
    repo.update_ref(_intent_ref(intent_id), oid, None)
    _register_attempt_resource(intent_id)
    return {**_intent_payload(intent_value), "commit": oid}


@cli.command(
    "intents",
    description="List declared intents",
    annotations={"readOnlyHint": True},
    terminal_renderer=_render_intents_plain,
)
def list_intents() -> list[dict[str, str | None]]:
    """List all declared intents in creation order."""
    repo = GitRepository.discover()
    return [_intent_payload(item) for item in repo.list_intents()]


@cli.command("checkpoint", description="Snapshot the worktree with intent metadata")
def create_checkpoint(
    intent_id: IntentOption | None = None,
    why: Why | None = None,
    attempt_id: Identifier | None = None,
    agent: Identifier | None = None,
    auto: bool = False,
) -> dict[str, str]:
    """Snapshot dirty work without changing HEAD, the index, or files.

    Args:
        intent_id: Existing intent receiving this checkpoint; inferred in auto mode.
        why: Single-line reason for the changes; inferred in auto mode.
        attempt_id: Parallel attempt lineage; defaults to the agent id.
        agent: Agent or person creating the checkpoint; inferred when omitted.
        auto: Read a hook payload from stdin and infer missing metadata.
    """
    repo = GitRepository.discover()
    payload = _read_auto_payload() if auto else {}
    resolved_agent = _resolve_agent(agent, payload)
    if auto:
        if intent_id is None:
            intent_id, intent_title, task_ref = _auto_intent(payload)
        else:
            intent_title = os.environ.get("WAYPOINT_TASK") or _payload_text(
                payload, "task", "task_description", "prompt"
            )
            intent_title = (intent_title or f"Automatic intent {intent_id}")[:200]
            task_ref = os.environ.get("WAYPOINT_TASK_REF") or _payload_text(payload, "task_id")
        why = why or _auto_why(payload)
        if repo.ref_oid(_intent_ref(intent_id)) is None:
            create_intent(
                intent_title,
                intent_id=intent_id,
                agent=resolved_agent,
                task_ref=task_ref,
            )
    if intent_id is None:
        raise ValueError("intent_id is required unless --auto can infer it")
    if why is None:
        raise ValueError("why is required unless --auto can infer it")
    intent_value = repo.read_intent(intent_id)
    attempt = attempt_id or os.environ.get("WAYPOINT_ATTEMPT") or resolved_agent
    validate_id(attempt, field="attempt id")
    ref = waypoint_ref(intent_id, attempt)
    previous = repo.ref_oid(ref)
    parent = previous or repo.head()
    tree = repo.snapshot_tree()
    if tree == repo.tree_oid(parent):
        if auto:
            return {
                "status": "skipped",
                "intent": intent_id,
                "attempt": attempt,
                "reason": "no worktree changes since the previous checkpoint",
            }
        raise WaypointError(
            f"No worktree changes since the previous {intent_id}/{attempt} checkpoint"
        )
    created_at = datetime.now(UTC)
    metadata = CheckpointMetadata(
        intent_id=intent_id,
        attempt_id=attempt,
        agent=resolved_agent,
        why=why,
        created_at=created_at,
        task_ref=intent_value.task_ref,
    )
    oid = repo.commit_tree(
        tree,
        metadata.commit_message(),
        parent_oid=parent,
        agent=resolved_agent,
        created_at=created_at,
    )
    repo.update_ref(ref, oid, previous)
    return {
        "intent": intent_id,
        "attempt": attempt,
        "checkpoint": oid,
        "why": metadata.why,
        "agent": resolved_agent,
        "ref": ref,
        "status": "checkpointed",
    }


@cli.command(
    "attempts",
    description="List attempts for an intent",
    annotations={"readOnlyHint": True},
    terminal_renderer=_render_attempts_plain,
)
def list_attempts(intent_id: IntentArgument) -> list[dict[str, str | int]]:
    """List competing attempt heads with cumulative diffstats.

    Args:
        intent_id: Intent whose attempts should be listed.
    """
    repo = GitRepository.discover()
    repo.read_intent(intent_id)
    results: list[dict[str, str | int]] = []
    for _, attempt_id, oid in sorted(repo.attempt_refs(intent_id), key=lambda item: item[1]):
        history = repo.checkpoint_history(intent_id, attempt_id, oid)
        latest = history[0]
        base = history[-1].parent_oid
        diffstat = (
            repo.run("diff", "--stat", "--format=", base, oid).stdout.strip().replace("\n", " · ")
        )
        results.append(
            {
                "intent": intent_id,
                "attempt": attempt_id,
                "checkpoint": oid,
                "checkpoints": len(history),
                "agent": latest.metadata.agent,
                "why": latest.metadata.why,
                "diffstat": diffstat,
            }
        )
    return results


def _attempt_graph_data(
    repo: GitRepository,
    *,
    intent_id: str | None = None,
    attempt_id: str | None = None,
) -> dict:
    """Build a nested intent → attempt → checkpoint graph for every host."""
    intents = repo.list_intents()
    if intent_id is not None:
        repo.read_intent(intent_id)
        intents = [item for item in intents if item.id == intent_id]
    graph_attempts: list[dict] = []
    for intent_value in intents:
        for _, current_attempt, oid in sorted(
            repo.attempt_refs(intent_value.id), key=lambda item: item[1]
        ):
            if attempt_id is not None and current_attempt != attempt_id:
                continue
            history = repo.checkpoint_history(intent_value.id, current_attempt, oid)
            lineage = []
            for checkpoint in reversed(history):
                metadata = checkpoint.metadata
                diffstat = (
                    repo.run(
                        "diff",
                        "--stat",
                        "--format=",
                        checkpoint.parent_oid,
                        checkpoint.oid,
                    )
                    .stdout.strip()
                    .replace("\n", " · ")
                )
                lineage.append(
                    {
                        "checkpoint": checkpoint.oid,
                        "agent": metadata.agent,
                        "why": metadata.why,
                        "created_at": _timestamp_text(metadata.created_at),
                        "diffstat": diffstat,
                    }
                )
            graph_attempts.append(
                {
                    "intent": intent_value.id,
                    "intent_title": intent_value.title,
                    "attempt": current_attempt,
                    "checkpoint": oid,
                    "checkpoints": lineage,
                }
            )
    return {
        "intents": [_intent_payload(item) for item in intents],
        "attempts": graph_attempts,
        "selected_intent": intent_id,
        "selected_attempt": attempt_id,
    }


@cli.command(
    "log",
    description="Read the append-only intent journal",
    annotations={"readOnlyHint": True},
    terminal_renderer=_render_log_plain,
)
def journal_log(
    limit: Annotated[int, Ge(1), Le(1000)] = 100,
    ctx: Context = None,
) -> list[dict]:
    """Read intent and checkpoint events in append order.

    Args:
        limit: Maximum number of newest events to return.
    """
    repo = GitRepository.discover()
    events = _journal_events(repo)
    if ctx is not None and ctx.is_interactive and ctx.format == "plain":
        rows = _timeline_rows(repo)
        if rows:
            ctx.run_app(
                reducer=timeline_reducer,
                template="timeline.kida",
                initial_state=TimelineState(rows=rows),
                env=_timeline_env(),
            )
    return events[-limit:]


@cli.command(
    "pick",
    description="Apply a winning attempt to the working tree",
    annotations={"destructiveHint": True},
)
def pick_attempt(
    attempt: AttemptArgument,
    force: bool = False,
    ctx: Context = None,
) -> dict:
    """Apply an attempt without changing HEAD or the index.

    Args:
        attempt: ATTEMPT when unique, otherwise INTENT/ATTEMPT.
        force: Overwrite only paths changed by the attempt when conflicts exist.
    """
    repo = GitRepository.discover()
    intent_id, attempt_id, oid = repo.resolve_attempt(attempt)
    if (
        ctx is not None
        and ctx.is_interactive
        and not ctx.confirm(f"Pick {intent_id}/{attempt_id} and update the working tree?")
    ):
        return {
            "status": "cancelled",
            "intent": intent_id,
            "attempt": attempt_id,
            "checkpoint": oid,
            "paths": [],
        }
    yield Progress(status=f"Inspecting {intent_id}/{attempt_id}", step=0, total=2)
    history = repo.checkpoint_history(intent_id, attempt_id, oid)
    yield Progress(status=f"Applying {len(history)} checkpoint(s)", step=1, total=2)
    paths = repo.apply_attempt(history[-1].parent_oid, oid, force=force)
    return {
        "status": "picked",
        "intent": intent_id,
        "attempt": attempt_id,
        "checkpoint": oid,
        "force": force,
        "paths": paths,
    }


@cli.command(
    "undo",
    description="Reverse one checkpoint delta in the working tree",
    annotations={"destructiveHint": True},
)
def undo_checkpoint(checkpoint: CheckpointArgument, ctx: Context = None) -> dict:
    """Reverse one checkpoint without changing HEAD or the index.

    Args:
        checkpoint: Unique Waypoint checkpoint id or prefix.
    """
    repo = GitRepository.discover()
    yield Progress(status=f"Resolving checkpoint {checkpoint}", step=0, total=2)
    resolved = repo.resolve_checkpoint(checkpoint)
    if (
        ctx is not None
        and ctx.is_interactive
        and not ctx.confirm(f"Undo checkpoint {resolved.oid[:12]} ({resolved.metadata.why})?")
    ):
        return {
            "status": "cancelled",
            "checkpoint": resolved.oid,
            "intent": resolved.metadata.intent_id,
            "attempt": resolved.metadata.attempt_id,
            "paths": [],
        }
    yield Progress(status=f"Reversing {resolved.metadata.why}", step=1, total=2)
    paths = repo.reverse_checkpoint(resolved)
    return {
        "status": "undone",
        "checkpoint": resolved.oid,
        "intent": resolved.metadata.intent_id,
        "attempt": resolved.metadata.attempt_id,
        "paths": paths,
    }


@cli.command(
    "why",
    description="Explain the newest checkpoint touching a path",
    annotations={"readOnlyHint": True},
)
def explain_why(target: TargetArgument) -> dict:
    """Find the newest journaled change touching PATH or PATH:LINE.

    Args:
        target: Repository-relative path, optionally followed by a line number.
    """
    repo = GitRepository.discover()
    path, line = _parse_target(repo, target)
    for checkpoint in repo.all_checkpoints():
        if repo.checkpoint_touches(checkpoint, path, line):
            metadata = checkpoint.metadata
            return {
                "path": path,
                "line": line,
                "checkpoint": checkpoint.oid,
                "intent": metadata.intent_id,
                "attempt": metadata.attempt_id,
                "agent": metadata.agent,
                "why": metadata.why,
                "created_at": _timestamp_text(metadata.created_at),
                "task_ref": metadata.task_ref,
            }
    location = f"{path}:{line}" if line is not None else path
    raise WaypointError(f"No Waypoint checkpoint touches {location!r}")


ATTEMPT_GRAPH_HTML = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Waypoint attempt graph</title>
    <style>
      :root {
        color-scheme: light dark;
        font-family: ui-sans-serif, system-ui, sans-serif;
        --accent: #7c5cff;
        --muted: color-mix(in srgb, CanvasText 58%, transparent);
        --line: color-mix(in srgb, CanvasText 22%, transparent);
        --panel: color-mix(in srgb, Canvas 88%, CanvasText 12%);
        --winner: #2da44e;
      }
      * { box-sizing: border-box; }
      body { margin: 0; padding: 1rem; background: Canvas; color: CanvasText; }
      main { display: grid; gap: 1rem; min-width: 18rem; }
      header { display: flex; flex-wrap: wrap; gap: .75rem; align-items: end; }
      h1 { margin: 0; font-size: 1.15rem; }
      label { display: grid; gap: .25rem; font-size: .75rem; color: var(--muted); }
      select, button { font: inherit; }
      select { min-width: 12rem; padding: .4rem; }
      button { border: 1px solid var(--line); border-radius: .4rem; padding: .4rem .6rem; background: var(--panel); color: inherit; cursor: pointer; }
      button:disabled { cursor: not-allowed; opacity: .55; }
      #lanes { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(12rem, 1fr); gap: .75rem; overflow-x: auto; padding-bottom: .25rem; }
      .lane { position: relative; display: grid; align-content: start; gap: .55rem; min-height: 11rem; padding: .75rem; border: 1px solid var(--line); border-radius: .6rem; background: var(--panel); }
      .lane[data-winner="true"] { border-color: var(--winner); box-shadow: 0 0 0 1px var(--winner); }
      .lane h2 { margin: 0; font-size: .95rem; }
      .checkpoint { position: relative; display: grid; gap: .12rem; width: 100%; text-align: left; background: Canvas; }
      .checkpoint::before { content: ""; position: absolute; left: -.42rem; top: 50%; width: .36rem; height: .36rem; border-radius: 50%; background: var(--accent); }
      .checkpoint small { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
      .actions { display: flex; gap: .4rem; margin-top: auto; }
      #convergence { display: grid; place-items: center; min-height: 3rem; border-top: 2px solid var(--line); color: var(--muted); font-size: .85rem; }
      #convergence[data-picked="true"] { border-color: var(--winner); color: var(--winner); font-weight: 700; }
      #detail { min-height: 5rem; padding: .75rem; border: 1px solid var(--line); border-radius: .6rem; }
      #detail h2 { margin: 0 0 .5rem; font-size: .95rem; }
      #detail p { margin: .25rem 0; }
      #status { margin: 0; color: var(--muted); font-size: .8rem; }
      @media (max-width: 34rem) { #lanes { grid-auto-flow: row; grid-auto-columns: auto; } }
    </style>
  </head>
  <body>
    <main>
      <header>
        <div><h1>Waypoint attempt race</h1><p id="status" aria-live="polite">Connecting to the host…</p></div>
        <label>Intent <select id="intent" disabled></select></label>
        <button id="refresh" type="button" disabled>Refresh</button>
      </header>
      <section id="lanes" aria-label="Parallel attempts"></section>
      <div id="convergence" aria-live="polite">Pick an attempt to converge the race.</div>
      <section id="detail" aria-live="polite"><h2>Checkpoint detail</h2><p>Select a checkpoint to inspect why it exists.</p></section>
    </main>
    <script>
      (() => {
        const pending = new Map();
        const intentSelect = document.querySelector("#intent");
        const lanes = document.querySelector("#lanes");
        const detail = document.querySelector("#detail");
        const convergence = document.querySelector("#convergence");
        const refresh = document.querySelector("#refresh");
        const status = document.querySelector("#status");
        let nextId = 1;
        let toolName = "attempt-graph";
        let pickToolName = "pick";
        let serverTools = false;
        let graph = { intents: [], attempts: [] };
        let winnerAttempt = "";

        function post(message) { window.parent.postMessage({ jsonrpc: "2.0", ...message }, "*"); }
        function request(method, params) {
          const id = nextId++;
          post({ id, method, params });
          return new Promise((resolve, reject) => {
            const timer = window.setTimeout(() => { pending.delete(id); reject(new Error(`${method} timed out`)); }, 10000);
            pending.set(id, { resolve, reject, timer });
          });
        }
        function notify(method, params = {}) { post({ method, params }); }
        function siblingTool(name, sibling) {
          const split = name.lastIndexOf(".");
          return split < 0 ? sibling : `${name.slice(0, split + 1)}${sibling}`;
        }
        function text(tag, value, className = "") {
          const node = document.createElement(tag);
          node.textContent = value;
          if (className) node.className = className;
          return node;
        }
        function showDetail(attempt, checkpoint) {
          detail.replaceChildren();
          detail.append(text("h2", `${attempt.attempt} · ${checkpoint.checkpoint.slice(0, 12)}`));
          detail.append(text("p", checkpoint.why));
          detail.append(text("p", `${checkpoint.agent} · ${checkpoint.created_at}`));
          detail.append(text("p", checkpoint.diffstat || "No diffstat"));
        }
        async function inspectAttempt(attempt) {
          if (!serverTools) return;
          status.textContent = `Inspecting ${attempt.attempt}…`;
          try {
            const result = await request("tools/call", { name: toolName, arguments: { intent_id: attempt.intent, attempt_id: attempt.attempt } });
            renderToolResult(result);
            status.textContent = `Showing ${attempt.attempt}.`;
          } catch (error) { status.textContent = error instanceof Error ? error.message : String(error); }
        }
        async function pickAttempt(attempt) {
          if (!serverTools) return;
          status.textContent = `Requesting pick for ${attempt.attempt}…`;
          try {
            const result = await request("tools/call", { name: pickToolName, arguments: { attempt: `${attempt.intent}/${attempt.attempt}` } });
            const data = result && result.structuredContent;
            if (data && data.status === "picked") {
              winnerAttempt = attempt.attempt;
              renderGraph(graph);
              status.textContent = `${attempt.attempt} picked.`;
            } else status.textContent = "Pick was cancelled or returned no structured result.";
          } catch (error) { status.textContent = error instanceof Error ? error.message : String(error); }
        }
        function renderGraph(data) {
          graph = data && typeof data === "object" ? data : { intents: [], attempts: [] };
          const currentIntent = graph.selected_intent || intentSelect.value || graph.intents?.[0]?.id || "";
          intentSelect.replaceChildren();
          for (const item of graph.intents || []) {
            const option = text("option", item.title || item.id);
            option.value = item.id;
            option.selected = item.id === currentIntent;
            intentSelect.append(option);
          }
          lanes.replaceChildren();
          const visible = (graph.attempts || []).filter((item) => !currentIntent || item.intent === currentIntent);
          for (const attempt of visible) {
            const lane = document.createElement("article");
            lane.className = "lane";
            lane.dataset.winner = String(attempt.attempt === winnerAttempt);
            lane.append(text("h2", attempt.attempt));
            for (const checkpoint of attempt.checkpoints || []) {
              const button = document.createElement("button");
              button.type = "button";
              button.className = "checkpoint";
              button.append(text("strong", checkpoint.checkpoint.slice(0, 12)));
              button.append(text("small", checkpoint.why));
              button.addEventListener("click", () => showDetail(attempt, checkpoint));
              lane.append(button);
            }
            const actions = document.createElement("div");
            actions.className = "actions";
            const inspect = text("button", "Inspect");
            inspect.type = "button";
            inspect.disabled = !serverTools;
            inspect.addEventListener("click", () => inspectAttempt(attempt));
            const pick = text("button", "Pick");
            pick.type = "button";
            pick.disabled = !serverTools;
            pick.addEventListener("click", () => pickAttempt(attempt));
            actions.append(inspect, pick);
            lane.append(actions);
            lanes.append(lane);
          }
          convergence.dataset.picked = String(Boolean(winnerAttempt));
          convergence.textContent = winnerAttempt ? `Winner: ${winnerAttempt}` : "Parallel attempts converge here after pick.";
          if (!visible.length) lanes.append(text("p", "No attempts for this intent."));
        }
        function renderToolResult(result) {
          const data = result && result.structuredContent;
          if (!data || typeof data !== "object") { status.textContent = "The tool returned no structured graph."; return; }
          renderGraph(data);
        }
        async function refreshGraph() {
          if (!serverTools) return;
          status.textContent = "Refreshing graph…";
          try {
            const args = intentSelect.value ? { intent_id: intentSelect.value } : {};
            const result = await request("tools/call", { name: toolName, arguments: args });
            renderToolResult(result);
            status.textContent = "Graph refreshed.";
          } catch (error) { status.textContent = error instanceof Error ? error.message : String(error); }
        }

        window.addEventListener("message", (event) => {
          if (event.source !== window.parent) return;
          const message = event.data;
          if (!message || message.jsonrpc !== "2.0") return;
          if (Object.hasOwn(message, "id") && pending.has(message.id)) {
            const entry = pending.get(message.id);
            pending.delete(message.id);
            window.clearTimeout(entry.timer);
            if (message.error) entry.reject(new Error(message.error.message || "Host error"));
            else entry.resolve(message.result);
            return;
          }
          if (message.method === "ui/notifications/tool-input") {
            const selected = message.params && message.params.arguments?.intent_id;
            if (typeof selected === "string") intentSelect.value = selected;
          } else if (message.method === "ui/notifications/tool-result") renderToolResult(message.params);
        });
        refresh.addEventListener("click", refreshGraph);
        intentSelect.addEventListener("change", refreshGraph);
        request("ui/initialize", {
          protocolVersion: "2026-01-26",
          appInfo: { name: "Waypoint attempt graph", version: "1.0.0" },
          appCapabilities: {},
        }).then((result) => {
          toolName = result?.hostContext?.toolInfo?.tool?.name || toolName;
          pickToolName = siblingTool(toolName, "pick");
          serverTools = Boolean(result?.hostCapabilities?.serverTools);
          refresh.disabled = !serverTools;
          intentSelect.disabled = !serverTools;
          notify("ui/notifications/initialized");
          renderGraph(graph);
          status.textContent = serverTools ? "Connected. Refresh or inspect an attempt." : "Connected with structured fallback; host tool calls unavailable.";
        }).catch((error) => { status.textContent = error instanceof Error ? error.message : String(error); });
      })();
    </script>
  </body>
</html>"""


@cli.ui_resource(
    "ui://waypoint/attempts",
    name="Waypoint attempt graph",
    description="Dependency-free parallel attempt DAG",
    meta=MCPAppResourceMeta(prefers_border=True),
)
def attempt_graph_view() -> str:
    """Return the static MCP Apps document for the attempt graph."""
    return ATTEMPT_GRAPH_HTML


@cli.command(
    "attempt-graph",
    description="Inspect the intent, attempt, and checkpoint graph",
    annotations={"readOnlyHint": True},
    ui=MCPAppToolMeta("ui://waypoint/attempts"),
)
def attempt_graph(
    intent_id: Identifier | None = None,
    attempt_id: Identifier | None = None,
) -> dict:
    """Return a nested graph for plain agents and optional Apps hosts.

    Args:
        intent_id: Optional intent to focus.
        attempt_id: Optional attempt to inspect within the selected intent.
    """
    if attempt_id is not None and intent_id is None:
        raise ValueError("intent_id is required when attempt_id is provided")
    return _attempt_graph_data(
        GitRepository.discover(),
        intent_id=intent_id,
        attempt_id=attempt_id,
    )


@cli.resource(
    "waypoint://intents",
    name="Waypoint intents",
    description="Declared Waypoint intents in creation order",
    mime_type="application/json",
)
def intents_resource() -> list[dict[str, str | None]]:
    """Read all declared intents."""
    return list_intents()


@cli.resource(
    "waypoint://journal",
    name="Waypoint journal",
    description="Append-only intent and checkpoint event view",
    mime_type="application/json",
)
def journal_resource() -> list[dict]:
    """Read the complete append-only journal."""
    return _journal_events(GitRepository.discover())


_ATTEMPT_RESOURCE_LOCK = threading.Lock()
_ATTEMPT_RESOURCE_URIS: set[str] = set()


def _register_attempt_resource(intent_id: str) -> None:
    """Register one stable per-intent resource under an explicit lock."""
    validate_id(intent_id, field="intent id")
    uri = f"waypoint://attempts/{intent_id}"
    with _ATTEMPT_RESOURCE_LOCK:
        if uri in _ATTEMPT_RESOURCE_URIS:
            return

        def read_attempts() -> list[dict[str, str | int]]:
            return list_attempts(intent_id)

        read_attempts.__name__ = f"attempts_{intent_id.replace('-', '_')}"
        cli.resource(
            uri,
            name=f"Attempts for {intent_id}",
            description=f"Competing Waypoint attempts for intent {intent_id}",
            mime_type="application/json",
        )(read_attempts)
        _ATTEMPT_RESOURCE_URIS.add(uri)


def _register_existing_attempt_resources() -> None:
    try:
        repo = GitRepository.discover()
    except WaypointError:
        return  # silent: importing for schema/verification is valid outside a Git repository
    for intent_value in repo.list_intents():
        _register_attempt_resource(intent_value.id)


_register_existing_attempt_resources()


if __name__ == "__main__":
    cli.run()
