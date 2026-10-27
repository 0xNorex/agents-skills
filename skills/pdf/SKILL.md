---
name: pdf
description: Read, create, merge, split, annotate, OCR or fill PDF documents. Use when the task operates on a PDF, not when PDF is only mentioned.
license: Proprietary. LICENSE.txt has complete terms
---

# PDF documents

Choose the requested operation; do not load every library's examples. Run bundled scripts from this skill's root, using absolute document paths as needed.

| Task | First choice / reference |
|---|---|
| Extract text | Installed `pdftotext -layout input.pdf output.txt`; use OCR if the pages are scans |
| Extract tables, merge/split/rotate, watermark, metadata | Relevant section in [operations](references/operations.md); reuse installed CLI or Python tools |
| Create PDF | ReportLab section in [operations](references/operations.md); embed fonts supporting the actual language |
| Fill forms | [Forms](forms.md) before editing field/widget structure |
| Advanced rendering, JavaScript or troubleshooting | Relevant section in [reference](reference.md) |

Preserve the original unless replacement was requested. Encryption/password operations require the user's intended input and output; don't put real passwords in chat, committed scripts or shell history. Check installed tools rather than assuming availability. Use `uv` for Python helpers and dependencies.

Verify output opens, expected page count/order and retained text/fields. For visual edits, form filling or document creation, render and inspect the affected pages. Report OCR uncertainty and missing renderers; nonzero file size alone is not acceptance.
