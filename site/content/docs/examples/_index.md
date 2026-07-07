---
title: Examples
draft: false
weight: 70
lang: en
type: doc
description: Runnable example applications and copy paths.
keywords: [examples, sample apps, cli, mcp, tui]
tags: [examples]
icon: package
---

The repository examples are copy paths for real projects. Start with the
smallest example that matches the job, then run `milo verify` after adapting it.

:::{cards}
:columns: 2
:gap: medium

:::{card} Minimal CLI
:icon: terminal
:link: https://github.com/lbliii/milo-cli/tree/main/examples/greet
:description: One typed command with schema, CLI, llms.txt, and MCP tests
:::{/card}

:::{card} Dual-mode Deploy CLI
:icon: rocket
:link: https://github.com/lbliii/milo-cli/tree/main/examples/deploy
:description: Human confirmation, MCP annotations, resources, prompts, and progress
:::{/card}

:::{card} Interactive MCP App
:icon: terminal
:link: https://github.com/lbliii/milo-cli/tree/main/examples/mcp_app
:description: One typed command with dependency-free interactive HTML, a ui:// resource, gateway-safe tool calls, and structured fallback
:::{/card}

:::{card} Task Manager
:icon: check
:link: https://github.com/lbliii/milo-cli/tree/main/examples/taskman
:description: Commands plus MCP resources over application state
:::{/card}

:::{card} Output Gallery
:icon: list
:link: https://github.com/lbliii/milo-cli/tree/main/examples/outputgallery
:description: Human, CI, JSON, and diagnostic output patterns
:::{/card}

:::{/cards}

See the repository [examples index](https://github.com/lbliii/milo-cli/tree/main/examples) for the full list.
