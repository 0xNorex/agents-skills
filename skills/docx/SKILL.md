---
name: docx
description: Read, create or edit Word (.docx/.doc) documents, including formatting, tracked changes and comments. Use for Word-file tasks, not generic reports or other formats.
license: Proprietary. LICENSE.txt has complete terms
---

# Word documents

Choose the branch before loading examples. Commands below run from this skill's root; use absolute input/output paths when the document is elsewhere.

| Task | Approach |
|---|---|
| Read text | `pandoc --track-changes=all input.docx -o output.md`; use XML only when structure or revision details matter |
| Convert legacy `.doc`, render pages, accept revisions | Read the Quick Reference section of [document guide](references/docx-guide.md) |
| Create a document | Read only Creating New Documents in [document guide](references/docx-guide.md) |
| Edit an existing document | Read only Editing Existing Documents in [document guide](references/docx-guide.md); for XML changes use [XML reference](references/xml-reference.md) |

Preserve existing formatting, relationships, revisions and comments unless changing them is requested. Use the user's author identity when supplied; otherwise use a neutral `Editor` label, not a model vendor name. Work on a copy and avoid overwriting the original by default.

Use existing tools/dependencies first. New-document examples use the Node `docx` package; check availability in the project rather than installing globally. Python helpers use `uv run --no-project python scripts/...` with required dependencies available in the selected environment.

For generated/modified DOCX, run `scripts/office/validate.py`. When layout matters, render with LibreOffice and inspect representative pages for clipping, tables, fonts and page breaks. Report missing tools or unverified layout honestly; text extraction alone does not validate rendering.
