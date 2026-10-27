---
name: clown-src
description: 授权范围内的 SRC 漏洞验证、Web/API 安全测试、白盒安全审计与中文漏洞报告。普通代码质量审查、技能审计和文案修改不触发。
---

# SRC 与白盒安全研究

依据业务意图、信任边界和可复核证据研究漏洞；不以扫描数量或报告数量替代有效分析。

## 边界与路由

先读 [研究边界](rules/security-research-context.md)。已明确的范围内自主推进，不重复盘问身份材料；范围不明时先做公开资料或本地代码分析，只澄清影响实际测试的边界。

| 任务 | 按需读取 |
|---|---|
| 黑盒 Web/API、集团 SRC | [范围与执行](rules/dig-scope-workflow.md)，需要类型选择时读 [价值与矩阵](rules/src-value-hunting.md) |
| 项目源码、框架安全审计 | [白盒流程](rules/researcher-blackbox-whitebox.md) |
| 已有漏洞证据，需要正式报告 | [报告格式](rules/vuln-report-format.md) |
| 需要创建任务产物或清理指定任务 | [目录与清理](rules/desktop-task-folder.md) |
| 用户要求沉淀可复用研究经验 | [知识维护](rules/hunt-iter.md) |
| 交互式浏览器操作 | [浏览器工具](rules/playwright-browser-mcp.md) |

规则在本技能的 `rules/`，知识在 `知识库/`；不依赖其他机器的 Grok 配置、账号、代理或桌面路径。工具先发现再调用，未配置不能视为已启用。

## 知识按入口选择

有相应业务入口或代码证据再读专题；不用每站通读整库。完整模块见 [知识索引](知识库/README.md)。

| 线索 | 模块 |
|---|---|
| 用户、租户、对象访问 | [IDOR](知识库/idor-test.md)、[认证](知识库/authbypass-test.md) |
| 查询、筛选、表达式 | [注入](知识库/injection-test.md) |
| URL 抓取、代理、预览 | [SSRF](知识库/ssrf-test.md) |
| 回显、富文本、可写内容 | [XSS](知识库/xss-test.md) |
| 上传、下载、文件路径 | [上传](知识库/file-upload-test.md)、[路径](知识库/path-traversal-lfi-test.md) |
| 支付、审核、状态机 | [逻辑](知识库/logic-test.md)、[竞态](知识库/race-condition-test.md) |
| 前端接口发现 | [JS 分析](知识库/js-reverse-guide.md) |
| GraphQL / WebSocket / OAuth | [GraphQL](知识库/graphql-test.md)、[WebSocket](知识库/websocket-test.md)、[OAuth/JWT](知识库/oauth-jwt-test.md) |
| Agent 工具或云 IDE RPC | [工具执行边界](知识库/agent-tool-exec-test.md)、[云 IDE](知识库/cloud-ide-codex-rce-chain.md) |
| 有差分的测试被 WAF 拦截 | [WAF](知识库/waf-bypass.md) |

知识库是方法参考，不覆盖研究边界、实际授权和用户当次要求。现有 SRC 偏好排除 CORS，见 [CORS 偏好](rules/cors-vuln-report-priority.md)。

## 完成

按本轮明确范围记录已验证、已证伪、未测和阻塞项；发现附位置、条件、证据、影响与修复。达到范围/预算/证据饱和边界就交付，不自动随机扩面。保护现有用户会话；测试写入限受控对象且有回滚方案，凭证和个人信息在交付中脱敏。
