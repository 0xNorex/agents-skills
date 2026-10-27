# agents-skills

个人 agent 技能库。`AGENTS.md` 是所有 skill 共用的全局规则（pi / 其他 harness 通过软链读同一份），`skills/` 下每个目录是一个 skill，入口为 `SKILL.md`。

安装到某台机器：把本仓库放到 `~/.agents`，再让 harness 的 AGENTS.md 指向 `~/.agents/AGENTS.md`。
