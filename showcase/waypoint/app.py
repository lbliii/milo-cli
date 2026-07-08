"""Waypoint — an agent-native intent journal layered over Git.

Git records what changed. Waypoint records why, which agent made the change,
and which parallel attempt produced it. Journal writes create Git objects and
atomically update only ``refs/waypoint/*``; they never mutate HEAD, the real
index, or the working tree. Only ``pick`` and ``undo`` change working-tree
files, and neither stages those changes.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Final

from milo import CLI, MaxLen, MinLen, Option, Pattern, Positional

_ID_EXPRESSION: Final = r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?"
_ID_PATTERN: Final = re.compile(_ID_EXPRESSION)
_OID_PATTERN: Final = re.compile(r"[0-9a-f]{7,64}")
_HUNK_PATTERN: Final = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_TRAILER_PREFIX: Final = "Waypoint-"
_META_REF_NAME: Final = "meta"
_DEFAULT_TIMEOUT: Final = 10.0
REF_NAMESPACE: Final = "refs/waypoint"

Identifier = Annotated[
    str,
    MinLen(1),
    MaxLen(64),
    Pattern(f"^{_ID_EXPRESSION}$"),
]
Title = Annotated[str, Positional("TITLE"), MinLen(1), MaxLen(200)]
IntentArgument = Annotated[str, Positional("INTENT"), MinLen(1), MaxLen(64)]
IntentOption = Annotated[
    str,
    MinLen(1),
    MaxLen(64),
    Pattern(f"^{_ID_EXPRESSION}$"),
    Option(aliases=("--intent",), metavar="ID"),
]
AttemptArgument = Annotated[str, Positional("ATTEMPT"), MinLen(1), MaxLen(129)]
CheckpointArgument = Annotated[
    str,
    Positional("CHECKPOINT"),
    MinLen(7),
    MaxLen(64),
    Pattern(r"^[0-9a-f]{7,64}$"),
]
TargetArgument = Annotated[str, Positional("PATH[:LINE]"), MinLen(1)]


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
    description="Record why agents changed a Git working tree.",
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
    agent: Identifier = "human",
    task_ref: str | None = None,
) -> dict[str, str | None]:
    """Declare a goal that one or more agents may attempt.

    Args:
        title: Human-readable goal.
        intent_id: Stable id; defaults to a unique slug of the title.
        agent: Agent or person declaring the intent.
        task_ref: Optional external issue or task reference.
    """
    repo = GitRepository.discover()
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
        agent=agent,
        task_ref=task_ref,
        created_at=created_at,
    )
    oid = repo.commit_tree(
        repo.tree_oid(parent),
        intent_value.commit_message(),
        parent_oid=parent,
        agent=agent,
        created_at=created_at,
    )
    repo.update_ref(_intent_ref(intent_id), oid, None)
    return {**_intent_payload(intent_value), "commit": oid}


@cli.command("intents", description="List declared intents", annotations={"readOnlyHint": True})
def list_intents() -> list[dict[str, str | None]]:
    """List all declared intents in creation order."""
    repo = GitRepository.discover()
    return [_intent_payload(item) for item in repo.list_intents()]


@cli.command("checkpoint", description="Snapshot the worktree with intent metadata")
def create_checkpoint(
    intent_id: IntentOption,
    why: Annotated[str, MinLen(1), MaxLen(500)],
    attempt_id: Identifier | None = None,
    agent: Identifier = "human",
) -> dict[str, str]:
    """Snapshot dirty work without changing HEAD, the index, or files.

    Args:
        intent_id: Existing intent receiving this checkpoint.
        why: Single-line reason for the changes.
        attempt_id: Parallel attempt lineage; defaults to the agent id.
        agent: Agent or person creating the checkpoint.
    """
    repo = GitRepository.discover()
    intent_value = repo.read_intent(intent_id)
    attempt = attempt_id or agent
    ref = waypoint_ref(intent_id, attempt)
    previous = repo.ref_oid(ref)
    parent = previous or repo.head()
    tree = repo.snapshot_tree()
    if tree == repo.tree_oid(parent):
        raise WaypointError(
            f"No worktree changes since the previous {intent_id}/{attempt} checkpoint"
        )
    created_at = datetime.now(UTC)
    metadata = CheckpointMetadata(
        intent_id=intent_id,
        attempt_id=attempt,
        agent=agent,
        why=why,
        created_at=created_at,
        task_ref=intent_value.task_ref,
    )
    oid = repo.commit_tree(
        tree,
        metadata.commit_message(),
        parent_oid=parent,
        agent=agent,
        created_at=created_at,
    )
    repo.update_ref(ref, oid, previous)
    return {
        "intent": intent_id,
        "attempt": attempt,
        "checkpoint": oid,
        "why": metadata.why,
        "agent": agent,
        "ref": ref,
    }


@cli.command(
    "attempts", description="List attempts for an intent", annotations={"readOnlyHint": True}
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
        diffstat = repo.run("diff", "--stat", "--format=", base, oid).stdout.strip()
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


@cli.command(
    "pick",
    description="Apply a winning attempt to the working tree",
    annotations={"destructiveHint": True},
)
def pick_attempt(attempt: AttemptArgument, force: bool = False) -> dict:
    """Apply an attempt without changing HEAD or the index.

    Args:
        attempt: ATTEMPT when unique, otherwise INTENT/ATTEMPT.
        force: Overwrite only paths changed by the attempt when conflicts exist.
    """
    repo = GitRepository.discover()
    intent_id, attempt_id, oid = repo.resolve_attempt(attempt)
    history = repo.checkpoint_history(intent_id, attempt_id, oid)
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
def undo_checkpoint(checkpoint: CheckpointArgument) -> dict:
    """Reverse one checkpoint without changing HEAD or the index.

    Args:
        checkpoint: Unique Waypoint checkpoint id or prefix.
    """
    repo = GitRepository.discover()
    resolved = repo.resolve_checkpoint(checkpoint)
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


if __name__ == "__main__":
    cli.run()
