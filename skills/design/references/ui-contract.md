# Product UI consistency

Use for dashboards, admin pages and data-heavy product surfaces. Extend the existing visual system rather than importing marketing-page styling rules.

## Find the reference

Read the nearest comparable page and its components/tokens. If the project has `docs/ui-system.md` or another UI specification, use it. A small change does not require a new design-system document.

Keep page width, spacing, typography, control sizes, radii and semantic colors consistent with that reference. Reuse table toolbars, pagination, form layout and empty states when present.

## Abstraction boundary

- Prefer existing primitives and patterns; do not duplicate a working PageHeader or DataTable.
- Create a shared pattern only when the current work has real reuse or a correctness reason. One local component is fine for a one-off surface.
- Follow the repository's component layout. Do not scaffold a prescribed `ui/patterns/features` tree or ten unused components.
- Use existing tokens. Add a token only for a meaningful new semantic role, not a one-pixel difference.
- New visual language belongs to an explicit redesign, not an incidental feature patch.

For interaction choices, read [UX patterns](ux-system.md). Verify the changed states with [visual QA](visual-qa.md), comparing against the reference page.
