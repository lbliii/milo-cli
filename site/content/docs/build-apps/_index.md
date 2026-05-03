---
title: Build Apps
draft: false
weight: 40
lang: en
type: doc
description: Build reducer-driven terminal apps with templates, input, forms, flows, commands, and sagas.
keywords: [apps, state, reducers, templates, forms, flows, sagas]
tags: [apps, tui]
icon: layers
---

Build interactive terminal applications with explicit state, pure reducers,
Kida templates, keyboard input, and effect boundaries.

:::{cards}
:columns: 2
:gap: medium

:::{card} State and Reducers
:icon: database
:link: ./state/
:description: Model app state and deterministic updates
:::{/card}

:::{card} Templates
:icon: layers
:link: ./templates/
:description: Render state with Kida terminal templates
:::{/card}

:::{card} Forms and Flows
:icon: check
:link: ./forms/
:description: Collect input and navigate multi-screen workflows
:::{/card}

:::{card} Commands and Sagas
:icon: workflow
:link: ./sagas/
:description: Run effects outside reducers
:::{/card}

:::{/cards}

:::{child-cards}
:include: pages
:fields: title, description, icon
:::
