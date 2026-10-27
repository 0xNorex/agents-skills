# Reusable blocks

Use only when the user requests a block collection or the current work has repeated page-level patterns. This package does not ship a populated `blocks/` implementation library.

Reuse the project's components first. For a genuinely reusable new block, follow its existing file layout and document only:

- When to use it and one working usage example.
- Its actual inputs and supported states.
- Responsive behavior, keyboard access and reduced-motion behavior when relevant.
- Existing tokens/dependencies it relies on.

Do not create a taxonomy, frontmatter schema, theme variants or component directories for hypothetical blocks. [Pattern vocabulary](vocabulary.md) names optional visual ideas; [visual QA](visual-qa.md) checks the result against the task, not a universal aesthetic checklist.
