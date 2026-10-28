---
name: spec-lite
description: Record the why and the boundaries of complex or critical work as one spec page per module plus ADRs, then verify the file graph with a script. Use only when work is multi-session, crosses module boundaries, changes a public contract, records a design decision, or is irreversible (data migration, protocol change, auth). Use for 写规格/spec/ADR/架构决策记录/模块边界. NEVER for small fixes, renames, single-file edits, bug hunts, or exploration — just do those.
---

# Spec-lite

Two artifacts, no tooling, no index, no RAG:

```
docs/spec/<module>.md       # one page per module: purpose, boundaries, invariants
docs/decisions/NNNN-<kebab>.md   # one file per decision: why
```

Code plus tests are the current state. Specs carry only what code cannot show; ADRs carry only why.

## Gate — run this before writing anything

Use this skill only if at least one holds:

1. Work spans sessions or days, and the next session cannot recover the intent from code.
2. The change crosses a module boundary or alters a shared contract (API, event, schema, CLI flag).
3. A decision will be questioned later: "why was this chosen over X?"
4. The change is irreversible: data migration, protocol change, auth/permission model, deletion.
5. An existing spec covers this area and the change makes it wrong.

If none hold, do not use this skill. Say nothing about specs and finish the task. A one-file bug fix never needs a page.

Never spec-first the whole repo. Write one page the first time a module is actually touched.

## Spec page — max 40 lines

```markdown
---
id: auth
type: module          # goal | architecture | module
title: Authentication
parent: architecture  # optional
depends-on: [db, session]   # optional, ids
status: active        # draft | active | stale | done
---

**Purpose** one sentence: what this module is for.

**Boundaries** what it may depend on, what it must never know about.

**Invariants** the rules that break silently if violated. Each one a claim a reviewer could check.

**Decisions** links to ADRs: `decisions/0007-session-in-redis.md` — one line why.
```

Write only what code cannot show: no file listing, no function-by-function walkthrough, no restating types, no "future work".

## ADR — one decision, one file

```markdown
# 0007 Session state in Redis

Status: accepted            # accepted | superseded by ADR-0012
Date: 2026-10-28

## Context   forces at play, in 2-4 lines
## Decision  what we do, one paragraph
## Consequences  what gets easier, what gets harder, what we accept
```

Append-only. To reverse a decision, write a new ADR and set the old one's `Status: superseded by ADR-NNNN`. Never edit an accepted ADR.

## Same change, both sides

Spec and code move in one commit. If code and spec disagree, fix both — never let them fork silently. A spec that has drifted out of date is worse than no spec: mark it `status: stale` the moment you know it lies.

## Verify

```bash
python3 ~/.agents/skills/spec-lite/check_specs.py docs
```

Checks unique ids, resolvable `parent` / `depends-on`, no cycles. Exit 0 prints `OK n specs`; exit 1 lists every error. Run it before claiming the change is done.
