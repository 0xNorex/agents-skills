---
name: thinking
description: Map a problem to one of 7 thinking frameworks in references/, or NONE. User-invoked router — not a catalog of separate skills.
disable-model-invocation: true
---

# Model Router

**Core rule:** Prefer NONE or one primary framework. Route by mechanism fit, not habit. Combine only when roles are distinct and necessary.

## When to Use

- The right framework is unclear and you would otherwise guess or stack tools.
- Several rows in the cheat-map seem plausible and you need a single primary (or explicit NONE).
- High-stakes work where a wrong frame is costly and a quick domain×type match helps.

## When NOT to Use

- The match is already known or obvious — read that `references/*.md` directly; do not route for show.
- The task is routine implementation with no analytical unknown — reason directly (NONE).
- You are mid-execution of an agreed plan and only need the next concrete step.

## 框架速查（7 个，全部有完整版在 references/）

| 场景信号 | 用这个 | 一句话机制 |
|----------|--------|-----------|
| 约束被当固定、要重新发明 | first-principles | 拆掉惯例，只留物理约束，重建最小解 |
| 计划/发布前找失败点 | pre-mortem | 假设已失败，反推原因 → 转成缓解与停止检查 |
| 预测、估算、风险大小 | probabilistic | 基率锚定，给区间，按证据更新 |
| 决策犹豫、两难 | reversibility | 先分可逆性：双向门快走，单向门留选项 |
| 变更有连锁影响 | second-order | 追后果链：激励、规模、反馈，带时间与概率 |
| 需求模糊、假设多、太「显然」 | socratic | 问承重问题，暴露隐藏需求再动手 |
| 跨组件涌现行为、修东坏西 | systems | 画边界/存量流量/反馈，找杠杆点 |

## Procedure

1. **Short-circuit.** One framework clearly fits by mechanism → return it alone. None clearly improves the work → **NONE**, reason directly. Stop.
2. **Match.** Otherwise scan the cheat-map above; pick the row whose signal matches the problem type (diagnose / decide / understand / create / evaluate / predict / optimize).
3. **Sanity-check.** If the match is forced or the fit is only nominal, return **NONE**. Do not force a frame; re-route at most once.
4. **Multi only as exception.** Add a second framework only when it answers a distinct question the primary leaves open. Cap at two. Near-neighbors and synonyms do not stack.

## Output

```text
outcome: NONE | one | multi
route: <framework slug or NONE>
why: <mechanism fit in one sentence>
```

## Verification

- **Falsify / stop:** If the route is habit or familiarity rather than mechanism fit, discard and return NONE. If multi entries lack distinct roles, collapse to the single best primary.
- **Over-application guard:** Do not route when the framework is already obvious. Do not return more than two frameworks. Do not cite frameworks not listed above. Do not treat the router as a prerequisite for reading a leaf `references/*.md`.

## References（框架完整版，按需读取）
- first-principles.md / systems.md / pre-mortem.md / probabilistic.md / reversibility.md / second-order.md / socratic.md（references/ 目录）
