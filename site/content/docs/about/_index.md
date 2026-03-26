---
title: About
draft: false
weight: 50
lang: en
type: doc
description: Architecture, design decisions, and the Elm Architecture pattern.
keywords: [about, architecture, elm, design]
tags: [about]
icon: info
---

Background on Milo's architecture, the Elm Architecture pattern, and design decisions.

| Aspect | Milo's approach |
|--------|----------------|
| **State** | Immutable dicts or frozen dataclasses — never mutated |
| **Updates** | Pure reducer functions — deterministic, testable |
| **Views** | [[ext:kida:|Kida]] templates — declarative, hot-reloadable |
| **Effects** | Generator-based sagas — explicit, composable, thread-pool parallel |
| **Concurrency** | Python 3.14t free-threading — no GIL contention |

:::{child-cards}
:include: pages
:fields: title, description, icon
:::
