---
name: verification-before-completion
description: Use when about to claim work is complete, fixed, passing or done — before committing, PRs, or reporting back. Requires running the real-path check and confirming output first. Evidence before assertions, always.
---

# Verification Before Completion

## Overview

**Core principle:** Evidence before claims, always.

**Violating the letter of this rule is violating the spirit of this rule.**

## The Iron Law

```
NO COMPLETION CLAIMS WITHOUT FRESH EVIDENCE FROM AN INDEPENDENT ORACLE
```

If you have not run the check in this message, you cannot claim it passes.

## The Gate Function

```
BEFORE claiming any status or expressing satisfaction:

1. IDENTIFY: What real path proves this claim — a command, an endpoint, a
   page, a conversation with the real thing? Who runs it besides the author?
2. RUN: Execute it fresh and complete. Read the whole output, the exit
   code, the actual bytes on screen.
3. BREAK: Hand it to someone (or some model) whose goal is to break it —
   empty, huge, missing, unauthorized, wrong case, symlink, race,
   concurrent, disconnect, replay, non-UTF-8, path escape, timeout.
4. VERIFY: Does the output confirm the claim?
   - If NO: State actual status with the failing output
   - If YES: State the claim WITH the evidence and name the oracle
5. ONLY THEN: Make the claim

Skip any step = lying, not verifying.
```

**The author is never the oracle.** Same agent writing it and checking it = no verification. If you cannot name who broke it and which real path proved it, write **未验** instead of a success claim.

## Common Failures

| Claim | Requires | Not Sufficient |
|-------|----------|----------------|
| It works | Real path output: the page, the CLI, the request, the bill | HTTP 200, "should work", your own reading of the diff |
| Bug fixed | The original symptom, reproduced again and now absent | Code changed, assumed fixed |
| Requirements met | Line-by-line checklist against the spec | Everything else passing |
| Refactor is neutral | An equivalence check independent of the new code | "Behavior is unchanged" |
| Build succeeds | Build command: exit 0 | Linter passing, logs look good |
| Linter clean | Linter output: 0 findings | Partial check, extrapolation |
| Agent finished | VCS diff shows the change, plus your own check | Agent reports "success" |
| Test proves something | The check fails without the change | Green suite, same-source assertion |

A gate that only greps for strings the implementation already contains, or asserts the current output equals itself, is a change detector, not an oracle.

## Red Flags — STOP

- Using "should", "probably", "seems to"
- Expressing satisfaction before verification ("Great!", "Perfect!", "Done!", etc.)
- About to commit/push/PR without verification
- Trusting an agent's or your own earlier success report
- Relying on partial verification
- Thinking "just this once", or "the tests pass so it's fine"
- Tired and wanting work over
- **ANY wording implying success without having run verification**

## Rationalization Prevention

| Excuse | Reality |
|--------|---------|
| "Should work now" | RUN the check |
| "I'm confident" | Confidence ≠ evidence |
| "Just this once" | No exceptions |
| "The tests are green" | Green proves the tests, not the product |
| "Linter passed" | Linter ≠ compiler ≠ working software |
| "Agent said success" | Verify independently |
| "I'm tired" | Exhaustion ≠ excuse |
| "Partial check is enough" | Partial proves nothing |
| "Different words so rule doesn't apply" | Spirit over letter |

## Key Patterns

**Real path:**
```
✅ Open the page / run the CLI / hit the endpoint → see <exact output> → "it works, oracle: <path>"
❌ "Should work now" / "Looks correct" / "200 OK"
```

**Bug fix:**
```
✅ Reproduce the symptom → fix → reproduce again → gone → report both observations
❌ "I changed the code where it broke"
```

**Delegated work:**
```
✅ Agent reports success → read the diff → run the real path yourself → report actual state
❌ Trust the agent's report
```

**Requirements:**
```
✅ Re-read the spec → checklist every line → report gaps or completion
❌ "Everything passes, done"
```

## When To Apply

**ALWAYS before:**
- ANY variation of success/completion claims
- ANY expression of satisfaction
- ANY positive statement about work state
- Committing, PR creation, task completion
- Moving to the next task
- Delegating to an agent, and after it answers

**Applies to:**
- Exact phrases
- Paraphrases and synonyms
- Implications of success
- ANY communication suggesting completion/correctness

---

Adapted from [obra/superpowers](https://github.com/obra/superpowers) `skills/verification-before-completion/SKILL.md` — MIT License, © 2025 Jesse Vincent. Test-suite evidence rows replaced with independent-oracle and real-path evidence.
