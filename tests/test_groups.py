"""Tests for command groups: nesting, dispatch, MCP, and llms.txt."""

from __future__ import annotations

import pytest

from milo.commands import CLI
from milo.groups import Group, GroupDef
from milo.llms import generate_llms_txt
from milo.mcp import _call_tool, _list_tools

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_cli_with_groups():
    """Build a CLI with nested groups for testing."""
    cli = CLI(name="bengal", description="Static site generator", version="0.3.0")

    @cli.command("init", description="Create new site")
    def init(name: str, template: str = "default") -> str:
        return f"Created {name} with {template}"

    site = cli.group("site", description="Site operations")

    @site.command("build", description="Build the site")
    def build(output: str = "_site") -> str:
        return f"Built to {output}"

    @site.command("serve", description="Start dev server")
    def serve(port: int = 4000, host: str = "localhost") -> str:
        return f"Serving on {host}:{port}"

    config = site.group("config", description="Configuration")

    @config.command("show", description="Show merged config")
    def config_show(profile: str = "default") -> str:
        return f"Config for {profile}"

    @config.command("validate", description="Validate config")
    def config_validate() -> str:
        return "Config valid"

    return cli


# ---------------------------------------------------------------------------
# Group creation and registration
# ---------------------------------------------------------------------------


class TestGroupCreation:
    def test_group_basic(self):
        g = Group("site", description="Site ops")
        assert g.name == "site"
        assert g.description == "Site ops"

    def test_group_command_registration(self):
        g = Group("site")

        @g.command("build", description="Build")
        def build():
            pass

        assert "build" in g.commands
        assert g.commands["build"].name == "build"

    def test_group_sub_group(self):
        g = Group("site")
        config = g.group("config", description="Config")
        assert "config" in g.groups
        assert config.name == "config"

    def test_group_aliases(self):
        g = Group("site")

        @g.command("build", description="Build", aliases=("b",))
        def build():
            return "built"

        assert g.get_command("b") is not None
        assert g.get_command("b").name == "build"

    def test_group_alias_on_group(self):
        g = Group("site")
        g.group("config", aliases=("cfg",))
        assert g.get_group("cfg") is not None
        assert g.get_group("cfg").name == "config"

    def test_add_group(self):
        parent = Group("site")
        child = Group("config", description="Config mgmt")
        parent.add_group(child)
        assert "config" in parent.groups

    def test_to_def(self):
        g = Group("site", description="Site ops")

        @g.command("build", description="Build")
        def build():
            pass

        sub = g.group("config")

        @sub.command("show", description="Show")
        def show():
            pass

        gdef = g.to_def()
        assert isinstance(gdef, GroupDef)
        assert gdef.name == "site"
        assert "build" in gdef.commands
        assert "config" in gdef.groups
        assert "show" in gdef.groups["config"].commands


# ---------------------------------------------------------------------------
# CLI with groups
# ---------------------------------------------------------------------------


class TestCLIGroups:
    def test_cli_group_creation(self):
        cli = CLI(name="app")
        site = cli.group("site", description="Site ops")
        assert "site" in cli.groups
        assert isinstance(site, Group)

    def test_cli_add_group(self):
        cli = CLI(name="app")
        g = Group("site")
        cli.add_group(g)
        assert "site" in cli.groups

    def test_get_command_dotted(self):
        cli = _make_cli_with_groups()
        cmd = cli.get_command("site.build")
        assert cmd is not None
        assert cmd.name == "build"

    def test_get_command_deep_dotted(self):
        cli = _make_cli_with_groups()
        cmd = cli.get_command("site.config.show")
        assert cmd is not None
        assert cmd.name == "show"

    def test_get_command_dotted_not_found(self):
        cli = _make_cli_with_groups()
        assert cli.get_command("site.nonexistent") is None
        assert cli.get_command("fake.build") is None

    def test_get_command_top_level_unchanged(self):
        cli = _make_cli_with_groups()
        cmd = cli.get_command("init")
        assert cmd is not None
        assert cmd.name == "init"

    def test_call_dotted(self):
        cli = _make_cli_with_groups()
        assert cli.call("site.build", output="/out") == "Built to /out"

    def test_call_deep_dotted(self):
        cli = _make_cli_with_groups()
        assert cli.call("site.config.show", profile="prod") == "Config for prod"

    def test_call_dotted_unknown(self):
        cli = _make_cli_with_groups()
        with pytest.raises(ValueError, match="Unknown command"):
            cli.call("site.fake")

    def test_walk_commands(self):
        cli = _make_cli_with_groups()
        walked = cli.walk_commands()
        paths = [path for path, _ in walked]
        assert "init" in paths
        assert "site.build" in paths
        assert "site.serve" in paths
        assert "site.config.show" in paths
        assert "site.config.validate" in paths


# ---------------------------------------------------------------------------
# Dispatch via run()
# ---------------------------------------------------------------------------


class TestCLIGroupDispatch:
    def test_run_top_level(self):
        cli = _make_cli_with_groups()
        result = cli.run(["init", "--name", "my-site"])
        assert result == "Created my-site with default"

    def test_run_group_command(self):
        cli = _make_cli_with_groups()
        result = cli.run(["site", "build", "--output", "/public"])
        assert result == "Built to /public"

    def test_run_nested_group_command(self):
        cli = _make_cli_with_groups()
        result = cli.run(["site", "config", "show", "--profile", "prod"])
        assert result == "Config for prod"

    def test_run_group_with_defaults(self):
        cli = _make_cli_with_groups()
        result = cli.run(["site", "build"])
        assert result == "Built to _site"

    def test_run_group_no_subcommand_shows_help(self, capsys):
        cli = _make_cli_with_groups()
        result = cli.run(["site"])
        assert result is None


# ---------------------------------------------------------------------------
# Parser structure
# ---------------------------------------------------------------------------


class TestCLIGroupParser:
    def test_parser_has_group_subparser(self):
        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        # Should parse group commands without error
        args = parser.parse_args(["site", "build", "--output", "x"])
        assert args.output == "x"

    def test_parser_nested_group(self):
        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        args = parser.parse_args(["site", "config", "show", "--profile", "dev"])
        assert args.profile == "dev"

    def test_parser_top_level_flags_still_work(self):
        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        args = parser.parse_args(["--llms-txt"])
        assert args.llms_txt is True


# ---------------------------------------------------------------------------
# MCP integration
# ---------------------------------------------------------------------------


class TestMCPWithGroups:
    def test_list_tools_includes_group_commands(self):
        cli = _make_cli_with_groups()
        tools = _list_tools(cli)
        names = [t["name"] for t in tools]
        assert "init" in names
        assert "site.build" in names
        assert "site.serve" in names
        assert "site.config.show" in names
        assert "site.config.validate" in names

    def test_list_tools_schema(self):
        cli = _make_cli_with_groups()
        tools = _list_tools(cli)
        build_tool = next(t for t in tools if t["name"] == "site.build")
        assert "output" in build_tool["inputSchema"]["properties"]

    def test_call_tool_dotted(self):
        cli = _make_cli_with_groups()
        result = _call_tool(cli, {"name": "site.build", "arguments": {"output": "/pub"}})
        assert result["content"][0]["text"] == "Built to /pub"
        assert "isError" not in result

    def test_call_tool_nested(self):
        cli = _make_cli_with_groups()
        result = _call_tool(cli, {"name": "site.config.show", "arguments": {"profile": "qa"}})
        assert result["content"][0]["text"] == "Config for qa"

    def test_hidden_group_commands_excluded(self):
        cli = CLI(name="app")
        g = cli.group("ops")

        @g.command("secret", description="Hidden", hidden=True)
        def secret():
            return "shh"

        @g.command("public", description="Public")
        def public():
            return "hi"

        tools = _list_tools(cli)
        names = [t["name"] for t in tools]
        assert "ops.public" in names
        assert "ops.secret" not in names


# ---------------------------------------------------------------------------
# llms.txt integration
# ---------------------------------------------------------------------------


class TestLlmsTxtWithGroups:
    def test_groups_create_sections(self):
        cli = _make_cli_with_groups()
        txt = generate_llms_txt(cli)
        assert "# bengal" in txt
        assert "## Site operations" in txt
        assert "**build**" in txt
        assert "**serve**" in txt

    def test_nested_groups_deeper_headings(self):
        cli = _make_cli_with_groups()
        txt = generate_llms_txt(cli)
        assert "### Configuration" in txt
        assert "**show**" in txt
        assert "**validate**" in txt

    def test_hidden_group_excluded(self):
        cli = CLI(name="app")
        cli.group("internal", hidden=True)

        @cli.command("public", description="Public")
        def public():
            pass

        txt = generate_llms_txt(cli)
        assert "internal" not in txt.lower()
        assert "public" in txt

    def test_top_level_commands_still_shown(self):
        cli = _make_cli_with_groups()
        txt = generate_llms_txt(cli)
        assert "## Commands" in txt
        assert "**init**" in txt


# ---------------------------------------------------------------------------
# ResolveResult types and dispatch
# ---------------------------------------------------------------------------


class TestResolveResult:
    """Verify _resolve_command_from_args returns correct discriminated types."""

    def test_resolves_command(self):
        from milo.commands import ResolvedCommand

        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        args = parser.parse_args(["init", "--name", "x"])
        result = cli._resolve_command_from_args(args)
        assert isinstance(result, ResolvedCommand)
        assert result.command.name == "init"

    def test_resolves_group(self):
        from milo.commands import ResolvedGroup

        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        args = parser.parse_args(["site"])
        result = cli._resolve_command_from_args(args)
        assert isinstance(result, ResolvedGroup)
        assert result.group.name == "site"

    def test_resolves_nested_group(self):
        from milo.commands import ResolvedGroup

        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        args = parser.parse_args(["site", "config"])
        result = cli._resolve_command_from_args(args)
        assert isinstance(result, ResolvedGroup)
        assert result.group.name == "config"

    def test_resolves_nested_command(self):
        from milo.commands import ResolvedCommand

        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        args = parser.parse_args(["site", "build"])
        result = cli._resolve_command_from_args(args)
        assert isinstance(result, ResolvedCommand)
        assert result.command.name == "build"

    def test_resolves_nothing_no_args(self):
        from milo.commands import ResolvedNothing

        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        args = parser.parse_args([])
        result = cli._resolve_command_from_args(args)
        assert isinstance(result, ResolvedNothing)
        assert result.attempted is None

    def test_resolves_nothing_preserves_fmt(self):
        from milo.commands import ResolvedNothing

        cli = _make_cli_with_groups()
        parser = cli.build_parser()
        args = parser.parse_args([])
        result = cli._resolve_command_from_args(args)
        assert isinstance(result, ResolvedNothing)
        assert result.fmt == "plain"


# ---------------------------------------------------------------------------
# Group bare invocation and help rendering
# ---------------------------------------------------------------------------


class TestGroupBareInvocation:
    def test_group_bare_shows_help_not_error(self):
        cli = _make_cli_with_groups()
        result = cli.invoke(["site"])
        assert result.exit_code == 0
        assert result.stderr == ""
        assert "build" in result.output
        assert "serve" in result.output

    def test_nested_group_bare_shows_help(self):
        cli = _make_cli_with_groups()
        result = cli.invoke(["site", "config"])
        assert result.exit_code == 0
        assert result.stderr == ""
        assert "show" in result.output
        assert "validate" in result.output

    def test_unknown_command_still_suggests(self):
        cli = _make_cli_with_groups()
        result = cli.invoke(["siet"])
        assert result.exit_code == 2
        assert "Did you mean" in result.stderr

    def test_root_no_args_shows_help(self):
        cli = _make_cli_with_groups()
        result = cli.invoke([])
        assert result.exit_code == 0
        assert "bengal" in result.output


class TestHelpSubcommandListing:
    def test_root_help_lists_commands_by_name(self):
        cli = _make_cli_with_groups()
        result = cli.invoke([])
        assert "init" in result.output
        assert "site" in result.output
        assert "_command" not in result.output

    def test_group_help_lists_subcommands_by_name(self):
        cli = _make_cli_with_groups()
        result = cli.invoke(["site"])
        assert "build" in result.output
        assert "serve" in result.output
        assert "_command_site" not in result.output

    def test_nested_group_help_lists_subcommands(self):
        cli = _make_cli_with_groups()
        result = cli.invoke(["site", "config"])
        assert "show" in result.output
        assert "validate" in result.output
        assert "_command_config" not in result.output

    def test_root_help_shows_options(self):
        cli = _make_cli_with_groups()
        result = cli.invoke([])
        assert "--verbose" in result.output
        assert "--help" in result.output

    def test_group_help_no_argparse_internals(self):
        """Group help should use registry data, not argparse positional args."""
        cli = _make_cli_with_groups()
        result = cli.invoke(["site"])
        assert "positional arguments" not in result.output
