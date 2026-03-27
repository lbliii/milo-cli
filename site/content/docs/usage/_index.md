---
title: Usage
draft: false
weight: 20
lang: en
type: doc
description: Guides for every major Milo feature — state, sagas, flows, forms, templates, and testing.
keywords: [usage, guides, state, sagas, flows, forms]
tags: [usage]
icon: code
---

Detailed guides for each part of the Milo framework. Start with [[docs/usage/state|State]] to understand the core architecture, then explore the features you need.

```mermaid
flowchart TB
    subgraph Core
        Store[Store]
        Reducer[Reducers]
        Middleware[Middleware]
    end

    subgraph UI
        Templates[Kida Templates]
        Forms[Forms]
        Input[KeyReader]
    end

    subgraph Effects
        Sagas[Sagas]
        ThreadPool[ThreadPoolExecutor]
    end

    subgraph Multi-Screen
        Flow[Flow]
        Screens[FlowScreens]
        Navigate[@@NAVIGATE]
    end

    subgraph AI["AI Integration"]
        MCP[MCP Server]
        Gateway[Gateway]
        LLMS[llms.txt]
    end

    Input -->|"@@KEY"| Store
    Store --> Reducer
    Reducer -->|state| Templates
    Reducer -->|ReducerResult| Sagas
    Sagas --> ThreadPool
    ThreadPool -->|"Put(action)"| Store
    Flow --> Screens
    Screens --> Reducer
    Navigate --> Flow
    Middleware -->|wraps| Store
    Forms -->|form_reducer| Reducer
    MCP -->|"tools/call"| Reducer
    Gateway -->|proxies| MCP
```

:::{child-cards}
:include: pages
:fields: title, description, icon
:::
