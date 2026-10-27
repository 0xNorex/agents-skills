---
name: design-quality-bar
description: Set and enforce an award-grade quality bar for a page, site or product-UI deliverable, using the awwwards / Webby / FWA judging dimensions as the reference and a self-check loop to close the gap. Use when the user asks for award-winning, portfolio-grade or 设计感十足 results, or when one-shot generated UI needs a verifiable finish line. Not for small local UI fixes.
---

# Design quality bar

Turn "make it award-worthy" into scored dimensions, collected evidence, and a loop that stops when the work actually meets the bar.

## The bar

Judge against published criteria, not adjectives.

- **awwwards** — Design 40%, Usability 30%, Creativity 20%, Content 10%; each site is scored by at least 18 jury members with the 3 scores furthest from the average discarded; Honorable Mention starts at 6.5/10.
- **Webby (Websites & Mobile Sites)** — Content, Structure and Navigation, Visual Design, Functionality, Interactivity, Innovation, Overall Experience; unweighted, judged as one experience.
- **FWA** — a judge panel average out of 100 with at least 20 judges; recent FWA of the Day projects land around 80–85.

Usability carries 30% and is where most submissions lose. Keyboard path, focus states, contrast, hierarchy that survives zoom-out, responsive behavior, loading/empty/error states, and real content are part of the bar, not cleanup after it. Decoration never substitutes for hierarchy: one dominant idea plus one memorable interaction beats a checklist of effects.

## Self-check loop

1. Freeze what is under review: routes, states, breakpoints, content source.
2. Collect evidence for the current state — desktop and narrow screenshots, interaction capture, real copy, and the relevant checks (performance trace, a11y tree, keyboard-only pass). Evidence, not recollection of the code.
3. Score each dimension against the bar, then write the specific defects that hold it down: component, where it shows, how to reproduce.
4. Fix the 1–3 highest `weight × gap` items only. Do not re-decorate a dimension that already clears the bar.
5. Re-collect evidence and re-score. Repeat.

Stop when every dimension clears the bar, or one full round moves no dimension by a meaningful amount, or the agreed round budget (default 3) runs out. Report the score table, the remaining gaps, and what was traded away. Never keep iterating on taste alone.

## Prompt tail

When the goal is one-shot generation, append this to the prompt and make the iteration explicit:

> 作为品质标准，目标是达到 awwwards、Webby Awards、FWA 获奖水准。按这些奖项的评审维度逐项自检并打分，反复提升直到达标；每轮汇报差距、改动与剩余短板，不得用占位内容或空转的装饰性动效充数。

## Checks before claiming the bar

- Grayscale pass, then a 25%-zoom pass: does the hierarchy survive without color and fine detail?
- Keyboard-only pass through the primary flow, including focus visibility and tab order.
- Narrow viewport (360–390px) plus one abnormally long content case.
- Loading, empty, error and success states of every async surface.
- Motion: one dominant idea, `prefers-reduced-motion` respected, no scroll hijack, no jank under CPU throttling.
- Copy is real, specific to the audience, and free of filler sections or invented metrics.

## Escalate

This skill owns only the standard, the scoring and the loop. For direction, tokens, motion systems and implementation passes read `../design/SKILL.md`, plus its `references/visual-qa.md` and `references/ai-tells.md` when auditing polish.
