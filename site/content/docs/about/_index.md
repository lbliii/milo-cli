---
title: About
draft: false
weight: 10
lang: en
type: doc
description: Philosophy, architecture, concepts, thread safety, and ecosystem.
keywords: [about, philosophy, architecture, concepts, lifecycle, thread safety]
tags: [about]
icon: info
---

Background on Milo's philosophy, architecture, concepts, free-threading model,
and ecosystem.

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
