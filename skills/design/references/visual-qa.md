# Visual QA

Use for changes to rendered layout, styling or interaction. Pure documentation and non-rendering changes do not need screenshots.

## Capture

Start the app with its existing development/test command and use the actual URL.

1. Reuse the project's screenshot/e2e tests or an available browser tool.
2. Otherwise use an installed browser or renderer. Do not download a new tool just because this checklist mentions it.
3. If capture is unavailable, report the blocker and the specific unverified states. Do not claim visual acceptance from source inspection.

View the resulting screenshots, not just their file names. Capture a representative desktop and narrow viewport for responsive changes; add supported themes and affected loading/empty/error states when relevant. A local icon correction need not trigger a whole-app screenshot matrix.

## Inspect

- Requested layout and content match the brief and closest reference page.
- Text, controls and images are not clipped, overlapping or unexpectedly overflowing.
- Contrast, labels, focus and action hierarchy remain clear.
- Assets load; mock data and generated illustrations are not presented as real evidence.
- Test interactions in the browser when changed: a screenshot alone cannot prove keyboard behavior, saving or error recovery.

Fix issues introduced by the change. Report checks run and screenshot paths; separate implementation status from any blocked visual verification. Use Lighthouse or a performance trace when changing critical assets, heavy animation or performance-sensitive code, not for every copy edit.
