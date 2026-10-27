---
name: diagram
description: Create, edit or render technical/business diagrams, including flows, sequences, architecture and ER models, using Mermaid, DOT, PlantUML or SVG.
---

# Diagrams

Use the source material's entities, relationships, boundaries and ordering. Preserve terminology; clarify only ambiguity that changes the model, otherwise state a small assumption.

## Choose the representation

| Need | Prefer |
|---|---|
| Flow, sequence, state, ER, class, timeline, mind map | Mermaid |
| Dense dependency/network graph or precise cluster layout | Graphviz DOT |
| Formal UML or existing PlantUML source | PlantUML |
| Custom visual not well represented above | Accessible SVG with title and meaningful labels |

Keep the user's existing diagram language unless conversion is requested. For syntax patterns, read only the matching section of [diagram patterns](references/diagram-patterns.md).

Use stable ASCII IDs and short readable labels. Show important decisions, failures and boundaries when present in the source, not invented complexity. Default to one useful diagram and editable source; image-only requests need not include source inline.

## Render and validate

For a requested file, run from the skill root with absolute paths for external inputs/outputs:

```bash
uv run --no-project python scripts/render_diagram.py input.mmd --format svg --out output.svg
uv run --no-project python scripts/render_diagram.py input.dot --format png --out output.png
uv run --no-project python scripts/render_diagram.py input.puml --format svg --out output.svg
```

Reuse installed renderers. If unavailable, deliver the source with the exact rendering limitation; do not claim an image exists. When rendering succeeds, inspect the output for clipping, unreadable labels and wrong edge ordering. A nonempty file alone does not validate meaning or layout.

Return the requested artifact/source, its path when saved, and only material assumptions. Do not force a report template or duplicate checklists onto simple diagram answers.
