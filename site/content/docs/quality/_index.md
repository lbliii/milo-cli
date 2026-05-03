---
title: Quality and Operations
nav_title: Quality
draft: false
weight: 50
lang: en
type: doc
description: Test, verify, debug, and operate Milo CLIs and apps.
keywords: [testing, verify, debugging, pipeline, deployment]
tags: [quality, operations]
icon: check-square
---

Use this section when a command already works and needs to be trusted by humans,
CI, and agents.

:::{cards}
:columns: 2
:gap: medium

:::{card} Testing
:icon: check-square
:link: ./testing
:description: Schema, dispatch, MCP, verify, snapshots, and replay
:::{/card}

:::{card} Pipeline
:icon: workflow
:link: ./pipeline
:description: Coordinate multi-phase workflows with dependencies and retries
:::{/card}

:::{card} Contracts and Debugging
:icon: bug
:link: ../reference/dispatch
:description: Inspect dispatch, schema, and error contracts
:::{/card}

:::{card} Error Codes
:icon: alert-triangle
:link: ../reference/errors
:description: Look up structured diagnostic codes and repair hints
:::{/card}

:::{/cards}

:::{child-cards}
:include: pages
:fields: title, description, icon
:::
