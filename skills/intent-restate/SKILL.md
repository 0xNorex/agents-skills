---
name: intent-restate
description: Restate the user's goal and the problem they are trying to solve in your own words before acting, and surface only the ambiguities that would change the work. Use for broad, multi-goal, ambiguous or hard-to-reverse requests, when the user changes direction mid-session, or when they ask what you think they want (用你自己的话重述我的目标 / 我试图解决什么问题 / 先说说我要什么).
---

# Intent restate

The cheapest way to avoid building the wrong thing is to say the goal back before touching it. Restating is not a preamble to the deliverable: it exposes a wrong assumption while that assumption is still free.

## When

- Broad or open-ended asks: "优化一下", "重构", "评估", "帮我搞个好网站".
- Several goals at once, or two requests whose costs trade against each other.
- Ambiguous scope: which repo, which environment, how far, and what must not change.
- Expensive or hard to undo: migrations, deletes, external writes, published artifacts.
- Direction changes mid-session, or a long context where the original goal has drifted.
- The user explicitly asks for it.

## What to write

Two to five lines, no headings, no plan:

- 目标：the outcome the user wants, in your own words.
- 问题：the problem underneath — the thing actually broken or missing.
- 边界：what you will leave alone, and the assumptions you are proceeding on.
- 确认：only if a single open question would change the shape of the work, ask that one.

Keep every statement traceable to the user's words or to facts read from the repo, and mark inference as inference. Then start work; a correct restatement is not a request for permission.

## Rules

- Paraphrase, never echo the user's sentences back in a new order; an echo proves nothing.
- Name the real target — which files, paths, service or environment — not a generic category.
- Separate "what was asked" from "what would actually fix it" when they differ; that difference is the useful part.
- Do not inflate the restatement into a design doc, task list or phase plan.
- Restating does not license scope creep: doing more than was asked still needs a reason.
- When your restatement is wrong, the user corrects two lines instead of a whole implementation. Realign instead of defending the draft.
- Skip it for small, unambiguous edits; the gate must cost less than the mistake it prevents.

## Anti-patterns

- Echoing the request in the same words, reordered.
- Listing features you plan to build instead of the problem to solve.
- Hedging with "你可能想要…" and then asking five questions.
- Restating and then waiting, when the user already gave enough to act on.
