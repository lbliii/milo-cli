"""Groups — nested command groups with hierarchical CLI structure.

Demonstrates: cli.group(), nested groups, group aliases, walk_commands.

    uv run python examples/groups/app.py repo list
    uv run python examples/groups/app.py repo create --name my-project
    uv run python examples/groups/app.py repo settings show
    uv run python examples/groups/app.py repo settings set --key default-branch --value develop
    uv run python examples/groups/app.py --llms-txt
"""

from __future__ import annotations

from milo import CLI

cli = CLI(
    name="ghub",
    description="A mini GitHub CLI — milo command groups example.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# Top-level commands
# ---------------------------------------------------------------------------


@cli.command("whoami", description="Show current user")
def whoami() -> str:
    return "user: octocat"


# ---------------------------------------------------------------------------
# `repo` group
# ---------------------------------------------------------------------------

repo = cli.group("repo", description="Repository operations", aliases=("r",))


@repo.command("list", description="List repositories", aliases=("ls",))
def repo_list(owner: str = "octocat", limit: int = 10) -> list[dict]:
    """List repositories for an owner."""
    return [
        {"name": f"{owner}/project-{i}", "stars": i * 42}
        for i in range(1, min(limit, 4) + 1)
    ]


@repo.command("create", description="Create a repository")
def repo_create(name: str, private: bool = False) -> dict:
    """Create a new repository."""
    return {"created": name, "private": private, "url": f"https://github.com/octocat/{name}"}


@repo.command("delete", description="Delete a repository")
def repo_delete(name: str, confirm: bool = False) -> dict:
    """Delete a repository (requires --confirm)."""
    if not confirm:
        return {"error": "Pass --confirm to delete"}
    return {"deleted": name}


# ---------------------------------------------------------------------------
# `repo settings` nested group
# ---------------------------------------------------------------------------

settings = repo.group("settings", description="Repository settings", aliases=("cfg",))


@settings.command("show", description="Show all settings")
def settings_show() -> dict:
    """Show current repository settings."""
    return {
        "default-branch": "main",
        "visibility": "public",
        "wiki": True,
        "issues": True,
    }


@settings.command("set", description="Update a setting")
def settings_set(key: str, value: str) -> dict:
    """Set a repository setting."""
    return {"updated": key, "value": value}


# ---------------------------------------------------------------------------
# `issue` group
# ---------------------------------------------------------------------------

issue = cli.group("issue", description="Issue operations", aliases=("i",))


@issue.command("list", description="List issues", aliases=("ls",))
def issue_list(state: str = "open", limit: int = 10) -> list[dict]:
    """List issues filtered by state."""
    return [
        {"number": i, "title": f"Bug #{i}", "state": state}
        for i in range(1, min(limit, 3) + 1)
    ]


@issue.command("create", description="Create an issue")
def issue_create(title: str, body: str = "") -> dict:
    """Create a new issue."""
    return {"number": 42, "title": title, "body": body, "state": "open"}


if __name__ == "__main__":
    cli.run()
