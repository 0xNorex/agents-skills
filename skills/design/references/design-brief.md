# Design brief and direction interview

Use this reference only when the request is greenfield, a visual overhaul, or an explicit request for a premium/distinctive direction. The goal is to remove high-impact guesses before implementation, not to collect a design-school questionnaire.

## Interview: first round

Ask no more than six questions at once. Prefer concrete choices and examples over abstract adjectives.

1. Who is the primary user, and what are they trying to finish on this screen?
2. What should the product be known for in one sentence? What should it never feel like?
3. Which page and action matter most right now? What must be visible above the fold?
4. Give two or three visual references and one anti-reference. Which exact qualities should be borrowed: typography, density, material, composition, motion, or tone?
5. What is fixed: brand colors, logo, copy, routes, data model, component library, light/dark mode, viewport, accessibility, or performance budget?
6. How far may the design vary from the existing UI? Choose targeted evolution, strong redesign, or visual overhaul with content/IA preserved.

Ask a second round only for unresolved high-impact decisions: dominant layout, density, palette/material, type direction, motion intensity, mobile priority, and acceptance criteria.

## Brief output

Before code, summarize:

- **Positioning:** one sentence describing audience, job, and emotional promise.
- **Design thesis:** one visual idea that makes the product recognizable.
- **Hierarchy:** primary action, supporting information, navigation, and progressive disclosure.
- **Visual system:** type roles, semantic colors, surfaces, spacing, radii, borders, shadows, icon treatment, and imagery.
- **Interaction:** one signature interaction plus ordinary states and keyboard behavior.
- **Responsive rule:** what remains primary when width or attention is reduced.
- **Content rule:** real copy/data shape, truncation, empty state, and prohibited invented evidence.
- **No-go list:** concrete patterns to avoid.
- **Acceptance check:** three to five observable criteria, not taste words.

Useful dials are optional descriptions, not requirements:

- `DESIGN_VARIANCE`: familiar / selective asymmetry / experimental
- `VISUAL_DENSITY`: spacious / balanced / dense
- `MOTION_INTENSITY`: direct / restrained / choreographed

## Premium-mode heuristics

- Start with composition and type; effects are a finishing layer.
- Use one hero material or surface treatment, not five competing ones.
- Prefer one strong accent and semantic status colors over a rainbow palette.
- Let empty space and alignment create confidence; do not fill every region.
- Use asymmetry only when it improves scanning or expresses the product's subject.
- Use motion for cause/effect, focus, or progress; honor reduced motion.
- If a detail cannot be explained by brand, task, or feedback, remove it.

## Implementation handoff

After the brief is accepted, ask the implementation agent to:

- inspect and reuse current tokens, primitives, routes, copy, and assets;
- build one representative state first;
- preserve existing behavior and analytics unless explicitly changed;
- include loading, empty, error, success, focus, and narrow-width states that the flow can reach;
- capture or inspect desktop and narrow screenshots before calling the design finished.

Do not add a new dependency, design-system package, illustration set, or animation library solely to make a page feel more premium.
