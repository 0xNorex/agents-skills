---
name: xlsx
description: Read, analyze, create or edit spreadsheet files (.xlsx, .xlsm, .csv, .tsv), including formulas, formatting and cleanup. Not for database pipelines or non-spreadsheet deliverables.
license: Proprietary. LICENSE.txt has complete terms
---

# Spreadsheet files

Analysis may return an answer; create a spreadsheet only when requested. Preserve existing templates, data types, formulas and macros/features needed by the user. Save a copy rather than overwriting the source by default.

| Task | Read only the relevant section |
|---|---|
| Read/analyze or clean tabular data | Reading and analyzing data / Best Practices in [workbook guide](references/workbooks.md) |
| Create/edit XLSX, formulas or formatting | Excel File Workflows in [workbook guide](references/workbooks.md) |
| Financial model | Financial models in [workbook guide](references/workbooks.md); existing template conventions take priority |
| Recalculate/check formulas | Recalculating formulas in [workbook guide](references/workbooks.md) |

Use existing libraries: stdlib CSV for simple delimited files, openpyxl for workbook-preserving edits, pandas for suitable data transformations. Commands in the guide run from this skill's root; use `uv` for Python.

For dynamic workbook calculations use formulas and explicit assumption cells. Static exports/CSV can contain computed values. Preserve leading-zero IDs and text types; never turn untrusted text beginning with formula syntax into an executable spreadsheet formula unintentionally.

Do not save a workbook loaded with `data_only=True` if formulas must survive. For `.xlsm`, preserve VBA (`keep_vba=True`) and check feature fidelity; do not run user macros. LibreOffice may alter Excel-only features: recalculate a copy when needed and verify compatibility before replacing anything.

Verify changed cells, row/column counts, data types and relevant formulas. Recalculate changed formulas with an available engine and check results, not just formula strings. Missing LibreOffice or unsupported formulas are explicit verification gaps, not permission to claim recalculation passed. Existing intentional error markers such as `#N/A` are not automatically defects to erase.
