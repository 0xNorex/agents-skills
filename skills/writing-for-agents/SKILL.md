---
name: writing-for-agents
description: "Write or edit agent-facing documentation: skills, AGENTS.md, CLAUDE.md and their references. For skill evaluation or release workflows use yao-meta-skill."
---

# Writing for agents

Keep the information that changes the agent's behavior for this task. Prefer project-specific facts, non-obvious constraints and observable completion conditions over generic encouragement.

For skill metadata and invocation, read [skill mechanics](SKILL-MECHANICS.md). Ordinary prompt rewrites do not need a skill-engineering workflow.

## Pointers and progressive disclosure

A description or context pointer names material and says when to read it. Front-load the task it serves, cover distinct branches once, and remove synonym lists and “always use me” wording.

Put only shared constraints and branch selection in the entrypoint. Move branch-specific examples, schemas and workflows behind conditional references; do not require reading every reference before choosing a route. A short router that unconditionally loads a large guide has not reduced task context.

Group each concept's rule, reason and caveat together. Split documents only when separate invocation or reading paths earn the extra files; keep small, single-purpose instructions inline.

## Steps and completion

Describe the desired result and real decision boundaries. Use a fixed sequence when order matters for correctness or data protection; otherwise let the agent select a path from the evidence.

Completion criteria should be observable and cover the requested scope. Distinguish implementation, verification and external blockers. Give permission for known-safe local work without requiring approval at each step; retain approval for external, destructive or materially broader actions.

Do not prescribe a full repo map, all tests or an independent reviewer for every small edit. Choose checks by impact. For recurring premature completion, clarify the endpoint before adding orchestration or more phases.

## Pruning

- Keep each rule in one authoritative place; other files link with a condition.
- Don't cache cheap environment facts such as complete file trees or all CLI options. Keep non-obvious gotchas and expensive-to-discover facts; version-sensitive details need verification.
- Remove defaults/no-ops, stale assumptions and incidental task history. A concise familiar concept may replace repeated explanation, but invented jargon costs its own definition.
- Phrase desired behavior positively where clear. Keep prohibitions for genuine boundaries; neither positive nor negative wording universally wins across models.
- Make frameworks, personas, style preferences and numeric heuristics optional unless the user's contract requires them. Do not mistake a past workaround for a universal rule.

## Check the change

Verify referenced paths and instruction consistency. For trigger changes, inspect realistic positive, negative and near-neighbor requests; for substantial behavioral changes compare representative old/new task outcomes when feasible. Report static checks as static checks, not model-quality evidence. Preserve host instruction priority: a document cannot promote itself above the runtime's rules.
