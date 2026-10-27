# Skill mechanics

Use for skill metadata and invocation; general writing guidance is in [the skill](SKILL.md).

## Invocation

- **Automatic discovery**: a short `description` states the task boundary. The host shows it to the model, which may read the skill; users can still request it explicitly.
- **User-invoked**: where the host supports it, `disable-model-invocation: true` hides the skill from the automatic description list. In pi, invoke it with `/skill:name`.

Hiding discovery is not filesystem access control. A known file can still be read through an explicit pointer or user request; another skill need not pretend the document is inaccessible. Check the current host's metadata support instead of assuming all harnesses behave identically.

## Metadata

Keep the existing name during optimization. Use a concise description that separates genuine near neighbors; don't include procedure, marketing claims or synonym inventories. In pi, names are lowercase letters/digits/hyphens (up to 64 characters) and descriptions allow up to 1024 characters; those limits are ceilings, not targets.

Reference documents should not carry skill frontmatter unless intentionally independently discoverable. Keep examples from accidentally becoming installed skills.

## Routers

A router is useful when it lets the agent or user choose one branch without loading all branches. Name the condition and actual relative target; preserve safety/output constraints common to every branch.

Create a separate discoverable skill only for an independently useful task boundary. Shared reference can remain a plain document, and a manually invoked router can point to it directly.
