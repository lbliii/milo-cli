---
title: Tutorials
draft: false
weight: 40
lang: en
type: doc
description: Step-by-step guides for building real CLI applications with Milo.
keywords: [tutorials, guides, examples]
tags: [tutorials]
icon: graduation-cap
---

Hands-on tutorials that walk you through building complete applications with Milo.

:::{cards}
:columns: 1-2
:gap: medium

:::{card} Build an Install Wizard
:icon: rocket
:link: ./build-a-wizard
:description: Multi-screen flow with forms, validation, and side effects
Build a three-screen installer using Flows, Forms, and Sagas — the full Milo stack.
:::{/card}

:::{card} Build a Counter App
:icon: keyboard
:link: ./build-a-counter
:description: Interactive terminal app with reducer state and Kida rendering
Build the smallest useful Milo app: key input, pure reducer, and live template rendering.
:::{/card}

:::{/cards}

:::{dropdown} Tutorial ideas
:icon: lightbulb

Have a tutorial you'd like to see? [Open an issue](https://github.com/lbliii/milo-cli/issues) with a description of what you'd like to build.

- Real-time status dashboard with `@@TICK` and sagas
- File browser with keyboard navigation and directory tree
- Test runner with watch mode, progress bars, and session recording
:::
