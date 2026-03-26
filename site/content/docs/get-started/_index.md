---
title: Get Started
draft: false
weight: 10
lang: en
type: doc
description: Install Milo and build your first interactive CLI app.
keywords: [get started, installation, quickstart]
tags: [onboarding]
icon: rocket
---

Install Milo with `pip install milo` (requires Python 3.14+), then create your first app with `milo dev`.

:::{cards}
:columns: 1-2
:gap: medium

:::{card} Installation
:icon: download
:link: ./installation
:description: Install with uv, pip, or from source
:badge: Step 1
Set up Milo and verify your Python 3.14t environment.
:::{/card}

:::{card} Quickstart
:icon: play
:link: ./quickstart
:description: Build a counter app in 5 minutes
:badge: Step 2
Write a reducer, create a template, and run your first interactive app.
:::{/card}

:::{/cards}

## Next steps

- [[docs/usage/state|State management]] — Store, middleware, combined reducers
- [[docs/usage/flows|Multi-screen flows]] — Chain screens with `>>`
- [[docs/usage/forms|Interactive forms]] — Collect structured input
- [[docs/usage/sagas|Sagas]] — Side effects with generators
