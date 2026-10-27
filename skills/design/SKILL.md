---
name: design
description: Design or redesign frontend pages and product UI, including motion and scroll choreography (animations, scroll effects, page transitions, hover and pointer interactions). Use for layouts, visual systems, dashboards and interaction design; not copy-only edits.
---

# Frontend design

Match the user's audience, brand, references and existing stack. For a redesign, preserve working routes, content, analytics and accessibility unless the requested change includes them. Ask only when preserve vs overhaul is genuinely unclear.

## Design direction gate

Do not start from vague requests such as “make it beautiful”, “premium” or “more modern”. Those are outcomes, not design decisions. For a greenfield page, a visual overhaul, or an explicit request for a more distinctive look, run a short design-direction interview before changing UI.

- Inspect the existing routes, tokens, components, content and current visual state first.
- Ask high-signal questions about positioning, user/job, primary action, visual references, anti-references, density, platform, motion, brand constraints, and what must not change.
- Ask in small rounds (up to 6 questions), then summarize the answers as a visual brief. Do not implement while a high-impact choice is unresolved.
- If the user has already supplied enough direction, infer the rest and state the assumptions instead of asking a questionnaire.
- For a small local UI fix, skip the interview and reuse the nearest working pattern.

Read [Design brief](references/design-brief.md) for the interview prompts, premium-mode heuristics, and implementation handoff.

## Premium and distinctive mode

When the brief asks for a high-end, tasteful, or unusual result, treat that as controlled art direction, not an effects checklist.

- Choose one dominant visual idea and one memorable interaction; keep the rest quiet.
- Establish hierarchy through typography, alignment, spacing, material contrast, and real content before adding gradients, glass, glow, or animation.
- Use a small token system: semantic surfaces, one accent family, a restrained type scale, a spacing rhythm, and a short radius/shadow scale.
- Provide positive references and at least one anti-reference. Extract principles; do not collage or imitate a named product.
- Remove generic AI tells: equal cards, decorative eyebrows, fake metrics, redundant badges, random gradients, excessive rounded corners, and filler sections.
- “Premium” must survive a grayscale and narrow-viewport check; decoration cannot carry the hierarchy.

## Build in passes

1. **Brief:** write the information hierarchy, content model, visual direction, tokens, states, responsive behavior, and no-go list. Do not write code yet.
2. **Representative surface:** implement one key route or state using existing primitives, real copy, and the smallest necessary CSS/component changes.
3. **Visual QA:** inspect desktop and narrow screenshots, plus relevant loading/empty/error/focus states. Fix clipping, hierarchy, contrast, density, and interaction issues before expanding the direction to sibling pages.
4. **Systemize only after proof:** promote repeated values or patterns into existing tokens/components; do not create a design system for a single screen.

## Route before reading

| Task | Read only what applies |
|---|---|
| Landing page, portfolio, visual refresh | [Visual guidance](references/ai-tells.md) |
| Dashboard, admin, data table, product UI | [UI contract](references/ui-contract.md); [UX patterns](references/ux-system.md) for interaction changes |
| Existing-site redesign or named visual pattern | [Vocabulary and redesign](references/vocabulary.md) |
| Motion or scroll choreography requested | [Motion examples](references/motion.md); optional [dials](references/dials.md) to describe intensity |
| Concrete palette, typography or chart recommendations | [Design database](references/uiux-db.md) |
| Need real reference sites, copy-paste component source or motion specifics | [Design sources](references/sources.md) |
| A particular design system is required | Its section in [official sources](references/appendix.md); verify current API before installation |
| User asks to maintain a reusable block collection | [Block guidance](references/block-library.md) |

## Implement

- Reuse the closest existing page, components and tokens. Use native HTML/CSS before adding libraries; keep the project's framework and package manager.
- Let hierarchy and content choose the layout. Avoid repeating a generic template, but do not replace clear tables, lists or familiar controls merely to look different.
- Images, animation and light/dark variants are scope choices, not mandatory features. Prefer supplied assets; generate missing visuals when needed or requested. Label mock data and generated product illustrations; never invent testimonials, customers or product evidence.
- Use semantic controls, labels, keyboard access, visible focus and readable contrast. Provide the loading/empty/error states that the changed flow can actually enter. Honor reduced-motion preferences for nonessential animation.
- Keep layout responsive without clipping text or hiding essential actions. Test the themes the project supports; do not add a theme system just for this task.
- Use CSS for simple motion. For JS animation, reuse installed tools, clean up listeners/timelines, avoid frame-by-frame React state updates, and keep expensive assets off the critical loading path.

## Finish

Run affected project checks and [visual QA](references/visual-qa.md) for rendered UI changes. Fix failures caused by the change; report unavailable checks separately from implementation status. A code-only review does not prove visual acceptance.
