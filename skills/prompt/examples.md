# Prompt 示例

完整 before/after，供改写时对照。

---

## 示例 1：模糊需求 → 可执行编码 prompt

### Before（D 级）

```
帮我修一下测试
```

### After（A 级）

```xml
<role>你是本仓库 Python 开发者，改动最小化</role>

<context>
- Python 3.12, FastAPI
- 测试：uv run pytest
- 失败用例：tests/test_auth.py::test_login_expired_token
- 相关实现：src/auth/service.py
</context>

<task>
修复 test_login_expired_token。只改 auth 模块。
</task>

<rules>
- MUST：保留 AuthService 公开 API 签名
- MUST：修完后跑 uv run pytest tests/test_auth.py
- MUST NOT：引入新依赖
- MUST NOT：删除或 skip 测试
- 不确定根因时先读代码，不要猜
</rules>

<verify>
uv run pytest tests/test_auth.py::test_login_expired_token 退出码 0
</verify>
```

### 改动理由

| 改动 | 原因 |
|------|------|
| 指定失败用例路径 | 「修测试」范围无穷 |
| 限定只改 auth 模块 | 防止 scope 膨胀 |
| MUST NOT 删测试 | 防止 agent 走捷径 |
| 验证写具体命令 | 「修好」变成可检查 |

---

## 示例 2：PR Review → 结构化审查 prompt

### Before（C 级）

```
review 这个 PR，看看有没有问题
```

### After（A 级）

```xml
<role>资深代码审查员；优先级：安全 > 正确性 > 可维护性</role>

<context>
- Python 3.12 + FastAPI
- 项目测试：uv run pytest
- 风格：已有 ruff 规则，不报 linter 已覆盖的风格问题
</context>

<task>审查下方 PR diff，只输出可行动发现。</task>

<rules>
- MUST：每条附 文件:行号
- MUST：分 Critical / Suggestion / Nit
- MUST NOT：报纯主观审美偏好
- 不确定是否问题时标「需确认」
</rules>

<input>
...粘贴 diff...
</input>

<output_format>
## Critical（必须修）
- [path:line] 问题 — 建议修复方式

## Suggestion（建议改）
- ...

## Nit（可选）
- ...
</output_format>

<verify>
每条 Critical 有具体行号；无 vague「整体不太好」类评论
</verify>
```

---

## 示例 3：格式漂移 → few-shot 锁定行为

### Before（B 级，易漂移）

```xml
<task>根据用户反馈生成 commit message</task>
<rules>遵循 conventional commits，简洁</rules>
```

### After（A 级）

```xml
<task>根据下方 diff 生成一条 commit message</task>

<rules>
- 格式：type(scope): subject + 空行 + body
- subject ≤ 72 字符，英文
- body 说明 why，不重复 diff
</rules>

<examples>
<example>
输入：新增 JWT 登录端点 + 中间件
输出：
feat(auth): add JWT login endpoint

Add POST /login and token validation middleware
</example>
<example>
输入：修复时区导致报表日期错误
输出：
fix(reports): correct timezone in date formatting

Use UTC timestamps consistently
</example>
<example name="edge_too_large">
输入：50 个文件的大重构
输出：
refactor(core): split monolith into service modules

Break UserService into auth, profile, and billing packages.
No behavior change; all existing tests pass.
</example>
</examples>

<input>
...git diff...
</input>

<output_format>纯文本，一条 commit message，不要解释</output_format>
```

---

## 示例 4：用户需求 → 可执行指令

### 用户原话

```
把这个项目的测试都搞绿，别动数据库迁移文件
```

### 改写后

```xml
<task>
本仓库所有 pytest 用例通过；不修改 db/migrations/ 下任何文件。
</task>

<context>
- 测试命令：uv run pytest
- 当前失败：先跑 pytest 获取失败列表
</context>

<rules>
- MUST：每个 checkpoint 只做一个 bounded 修复
- MUST NOT：修改 db/migrations/
- MUST NOT：删除、skip、xfail 测试来「搞绿」
</rules>

<verify>
uv run pytest 退出码 0
git diff --name-only 不包含 db/migrations/
</verify>
```

---

## 示例 5：反模式对照

| Before ❌ | After ✅ |
|-----------|----------|
| 你是世界上最厉害的程序员 | 你是本仓库 Python 开发者，风格对齐 src/ |
| 优化一下性能 | 将 /api/search P99 延迟从 800ms 降到 <200ms，用 profiling 数据支撑 |
| 完成后告诉我 | `uv run pytest` 退出码 0 才算完成 |
| 尽量保持简洁 | 输出 ≤300 字，给移动端阅读 |
| 写得好一点 | 按 `<output_format>` 模板，字段不可缺 |
