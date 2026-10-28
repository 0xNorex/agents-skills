---
name: writing-plans
description: Turn a spec or requirements into a task-by-task implementation plan before touching code — exact commands, file:line targets, expected output, and who verifies each task. Use for multi-step work, 写实施计划, 拆任务, or when a plan must survive handing to another agent.
---

# Writing Plans

## Overview

Write plans for an engineer who has not seen this codebase or this spec. Assume they write idiomatic code in the project's language once they know the exact interface and the exact thing to check, and that they will make a reasonable choice wherever the plan leaves one open. What they cannot know is what you decided: which files, which names and signatures, which values from the spec, which command proves each task. Document those. Give them the whole plan as bite-sized tasks. DRY. YAGNI.

**Announce at start:** "正在用 writing-plans 写实施计划。"

**Save plans to:** `docs/plans/YYYY-MM-DD-<feature-name>.md` — a project convention for plan location overrides this.

## Scope Check

If the spec covers multiple independent subsystems, suggest breaking it into separate plans — one per subsystem. Each plan should produce working software on its own.

## File Structure

Before defining tasks, map out which files will be created, modified or deleted and what each one is responsible for. This is where decomposition decisions get locked in.

- Design units with clear boundaries and well-defined interfaces. Each file has one clear responsibility.
- You reason best about code you can hold in context at once, and edits are more reliable when files are focused. Prefer smaller, focused files over large ones that do too much.
- Files that change together live together. Split by responsibility, not by technical layer.
- In existing codebases follow established patterns. If the codebase uses large files, don't unilaterally restructure — but if a file you're modifying has grown unwieldy, a split can be part of the plan.

## Task Right-Sizing

A task is the smallest unit that produces **something a fresh reviewer could accept or reject on its own**. Fold setup, configuration, scaffolding and documentation into the task whose deliverable needs them; split only where a reviewer could meaningfully reject one task while approving its neighbor. Every task carries its own acceptance method.

## Step Granularity

**Each step is one action with a checkable result:**

- "Change `src/api.ts:120` — `fetchUser(id: string): Promise<User>` calls the wrong endpoint" — a step
- "Run `<exact command>`, expect `<exact output>`" — a step
- "Open `<real surface>` (page, endpoint, CLI, device), expect `<what a person sees>`" — a step
- "Commit" — a step

A step whose result you cannot state in advance is not a step.

## Plan Document Header

**Every plan starts with this header:**

```markdown
# [Feature Name] Implementation Plan

**Goal:** [One sentence describing what this builds]

**Architecture:** [2-3 sentences about approach]

**Tech Stack:** [Key technologies/libraries]

**Spec:** [path to the design doc this plan implements — the plan argues
from the spec, so the spec travels with it; executors read both]

## Global Constraints

[Project-wide requirements — version floors, dependency limits, naming and
copy rules, platform requirements — one line each, exact values copied
verbatim from the spec. Every task implicitly includes this section.]

## Acceptance Gate

[For each task below: the real path that proves it works, and who breaks it
on purpose. Named as a command or a surface plus the expected observation —
"POST /api/x returns 201 and the row exists in the DB", not "works".
A task with no such line is unfinished planning, not a task.]

## Review Focus

[The input classes or failure modes the spec implies but no task's
acceptance line exercises, most likely to bite first: empty, oversized,
missing, unauthorized, case, symlink, race, disconnect, replay, non-UTF-8,
path escape, timeout. The spec says what the software must do, not
everything it will meet, and its silence on an input is not permission for
that input to break the program.]
```

## Task Structure

````markdown
### Task N: [Component Name]

**Files:**
- Create: `exact/path/to/file.py`
- Modify: `exact/path/to/existing.py:123-145`
- Delete: `exact/path/to/dead.py`

**Interfaces:**
- Consumes: [what this task uses from earlier tasks — exact signatures]
- Produces: [what later tasks rely on — exact function names, parameter
  and return types. A task's implementer sees only their own task; this
  block is how they learn the names and types neighboring tasks use.]

- [ ] **Step 1: Implement `load_config(path: str) -> Config` in `src/config.py`**

One line on the approach when the signature leaves a real choice (which
library call, which data structure); a code block only for an algorithm
they cannot determine.

- [ ] **Step 2: Verify**

Run: `uv run python -m app.cli --config ./fixtures/min.yaml`
Expect: exit 0, prints `loaded 3 keys`, `~/.cache/app/` untouched

- [ ] **Step 3: Commit**

```bash
git add src/config.py
git commit -m "feat(config): load config from yaml file"
```
````

## What a Step Contains

A step is done when the implementer can do exactly one reasonable thing from it. That is the whole requirement: unambiguous, not complete.

- **A code step:** the exact signature (name, parameters, return type), the file it lives in, and the specific values the spec pins. The implementer writes the body. A body appears only for an algorithm the signature does not determine, or for exact copy the spec fixes.
- **A verification step:** the command to run (or surface to open) and the output that means it passed.
- **A reference to another task:** that task's Interfaces block says what to use; the plan does not repeat that task's code.

A plan is the set of decisions the implementer cannot make alone. A plan longer than the code it describes has written the code instead. Lines that decide nothing ("TBD", "handle edge cases", "add appropriate validation", a type or function no task defines) are the opposite failure, and the self-review catches both.

## Self-Review

Run this yourself with fresh eyes — not a subagent dispatch.

**1. Spec coverage:** Skim each requirement in the spec. Point to the task that implements it. List gaps.

**2. Step scan:** Every step must let the implementer do exactly one thing. A line that decides nothing is a gap; a function body the signature already determines is a transcript. Fix both.

**3. Command viability:** Every verification command is copy-pasteable and currently runnable — real paths, real flags, and it fails for the right reason before the change.

**4. Naming consistency:** Types, signatures and property names in later tasks match what earlier tasks define. `clearLayers()` in Task 3 and `clearFullLayers()` in Task 7 is a bug.

**5. Review Focus:** Each line there is pinned to the task that owns the code, in that task's acceptance step. An empty section means you checked and found none, not that you skipped the check.

**6. Proportion:** A plan several times longer than the spec is a transcript of the program, not a plan. If code blocks dominate, replace bodies with signatures and check each step is still unambiguous.

Fix issues inline. No re-review needed.

## Execution Handoff

Save, self-review, then link the plan and let the human pick:

- **Subagent-driven** — a fresh agent implements each task and a different agent tries to break it before the next starts, then a whole-branch review. Most thorough; costs a fresh context per task.
- **Native** — implement every task in this session, then one independent pass on the whole branch. Cheapest and fastest; no independent review until the end.

Recommend one in a sentence, based on how much tasks depend on each other's interfaces and what a shipped mistake costs. Wait for the answer and for plan sign-off before implementing.

---

Adapted from [obra/superpowers](https://github.com/obra/superpowers) `skills/writing-plans/SKILL.md` — MIT License, © 2025 Jesse Vincent. TDD test-cycle steps replaced with real-path verification steps.
