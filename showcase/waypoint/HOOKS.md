# Automatic Waypoint Checkpoints

Waypoint's `checkpoint --auto` mode accepts a hook event as JSON on stdin. It
infers the agent from `agent_id` or `session_id`, the intent from a task/session
field or `WAYPOINT_INTENT`, and the reason from the tool call or final assistant
summary. If no files changed, it returns a structured `skipped` result instead
of failing the hook.

## Claude Code

Claude Code command hooks receive common fields including `session_id`, `cwd`,
and `hook_event_name`. `PostToolUse` also supplies `tool_name` and `tool_input`;
`Stop` supplies `last_assistant_message`. See the current
[Claude Code hooks reference](https://code.claude.com/docs/en/hooks).

Replace the two absolute paths below with the Milo checkout's virtual-environment
Python and Waypoint app, then add this to `.claude/settings.json`:

```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "\"/absolute/path/to/milo-cli/.venv/bin/python\" \"/absolute/path/to/milo-cli/showcase/waypoint/app.py\" checkpoint --auto --format json"
          }
        ]
      }
    ],
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"/absolute/path/to/milo-cli/.venv/bin/python\" \"/absolute/path/to/milo-cli/showcase/waypoint/app.py\" checkpoint --auto --format json"
          }
        ]
      }
    ]
  }
}
```

No agent prompt or explicit `wp checkpoint` call is needed. The hook JSON is
piped directly to Waypoint. `PostToolUse` records edit-bearing tool calls;
`Stop` captures the final `last_assistant_message` and safely skips when the
same tree was already checkpointed.

For a stable task-level intent shared across sessions, set these in the
harness environment:

```bash
export WAYPOINT_INTENT=issue-100
export WAYPOINT_TASK="Build the Waypoint agent surface"
export WAYPOINT_TASK_REF=milo-cli#100
```

Without `WAYPOINT_INTENT`, the hook's task or session id becomes the intent.
Set `WAYPOINT_ATTEMPT` to group several sessions into one attempt, or pass
`--agent some-id` to override inferred identity explicitly.

## Conductor

[Conductor is the workspace layer above its configured harness](https://www.conductor.build/docs/reference/harnesses).
When a Conductor workspace uses Claude Code, commit the same
`.claude/settings.json` in that workspace; each parallel workspace writes only
its own checkout's `refs/waypoint/*`. For another Conductor harness, configure
its equivalent post-tool/stop hook to pipe one JSON object to the same
`checkpoint --auto` command. Waypoint accepts the common `session_id`,
`agent_id`, `tool_name`, `tool_input`, `hook_event_name`, and
`last_assistant_message` fields and ignores unrelated fields.

## Safety

- Hook input is bounded to 1 MB and parsed as data; it is never evaluated by a
  shell or interpolated into a Git command.
- Automatic intent and checkpoint ids use the same constrained ref-safe format
  as explicit commands.
- Parallel ref updates use Git compare-and-swap. A stale writer fails rather
  than replacing another agent's checkpoint.
- Hooks create commit objects and `refs/waypoint/*`; they do not move HEAD,
  stage files, or rewrite the working tree.
