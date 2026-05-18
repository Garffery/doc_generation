---
name: erlang-backend-doc
description: >-
  Erlang/OTP backend technical document conventions. Use when generating backend
  dev docs for game servers, activities, or Erlang services — requirement briefs
  and draft reports should follow OTP-oriented structure and terminology.
---

# Erlang Backend Document Skill

When writing requirement briefs or backend development document drafts for Erlang/OTP systems:

## Requirement brief (research_brief)

- Prefer **functional points** that map to OTP boundaries: gen_server modules, supervisors, ETS/Mnesia usage, RPC/API handlers.
- Call out **process lifecycle**, **message flows**, and **supervision** when the feature implies long-running state.
- Use terms: `gen_server`, `supervisor`, `ETS`, `Mnesia`, `application`, `release`, `hot code upgrade` only when relevant.

## Draft report (draft_report)

For each F-xxx section include when applicable:

| Subsection | Erlang focus |
|------------|----------------|
| 模块划分 | application / supervisor / worker module names (suggested) |
| 接口设计 | HTTP/RPC handler module, request/response records or maps |
| 领域逻辑 | gen_server callbacks, cast/call patterns, state transitions |
| 数据设计 | ETS/Mnesia tables, record definitions, key constraints |
| 依赖与调用 | inter-module calls, cluster RPC, external HTTP |
| 异常与边界 | `{ok, _}` / `{error, _}` conventions, timeouts, crash recovery |

## Style

- Do not prescribe Java/Spring patterns unless the brief explicitly requires them.
- Mark OTP-specific choices as **建议/待确认** when not stated in the requirement brief.
