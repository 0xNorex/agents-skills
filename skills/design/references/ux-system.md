# Product interaction patterns

Use for changes to a user flow, not as a prerequisite for every CSS edit.

Identify the user's main task and the closest working flow. Reuse its information architecture unless changing it is part of the request.

| Situation | Prefer |
|---|---|
| Frequent action | Visible, reachable control |
| Rare action | Secondary action or overflow menu |
| Comparable records | Table/list with useful filtering and clear reset |
| Small local edit | Inline editing when validation and cancellation remain clear |
| Complex edit | Existing dialog, sheet or dedicated page pattern; field count alone is not decisive |
| Reversible removal | Undo when restoration is reliable |
| Irreversible or high-impact operation | Explicit confirmation proportional to risk |
| Loading | Stable layout and appropriate progress feedback |
| Empty data | Explain why and offer the next useful action |
| Error | Preserve user input; explain recovery |
| Success | Visible result or confirmation, without redundant interruption |

## Review the changed flow

- Main action is identifiable; destructive actions are not easy to confuse with it.
- Keyboard, focus, labels, validation, cancellation and recovery work.
- Relevant loading/empty/error/success states are covered; do not invent states for a static surface.
- Mobile layout preserves useful information and reachable controls.
- No unnecessary fields, navigation detours or new interaction convention.

Use [visual QA](visual-qa.md) for observable states. Independent review is useful for complex or risky flows, not mandatory for every edit. Persist a new pattern only when it is genuinely reusable; do not auto-write a spec after every task.
