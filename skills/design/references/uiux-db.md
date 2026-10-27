# uiux-db 数据库用法

（从原 ui-ux skill 合并而来，按需加载）

## 前置

```bash
python3 --version || python --version
```

无 Python 时先安装（macOS: `brew install python3`；Ubuntu: `sudo apt install python3`；Windows: `winget install Python.Python.3.12`）。

## Step 1：生成设计系统（REQUIRED）

```bash
python3 uiux-db-scripts/search.py "<product_type> <industry> <keywords>" --design-system [-p "Project Name"]
```

流程：并行搜 5 域（product/style/color/landing/typography）→ 按 `ui-reasoning.csv` 推理规则选优 → 返回完整设计系统（pattern/style/colors/typography/effects + 反模式）。

**示例：** `python3 uiux-db-scripts/search.py "beauty spa wellness service" --design-system -p "Serenity Spa"`

## Step 2：持久化（Master + Overrides 模式）

```bash
python3 uiux-db-scripts/search.py "<query>" --design-system --persist -p "Project Name" [--page "dashboard"]
```

生成 `design-system/MASTER.md`（全局源）和 `design-system/pages/<page>.md`（页面覆盖）。

层级检索：先查 `pages/<page>.md` → 有则覆盖 Master → 无则只用 Master。

## Step 3：按域补充搜索

```bash
python3 uiux-db-scripts/search.py "<keyword>" --domain <domain> [-n <max_results>]
```

| 需要 | domain | 示例 |
|------|--------|------|
| 更多风格 | `style` | `--domain style "glassmorphism dark"` |
| 图表建议 | `chart` | `--domain chart "real-time dashboard"` |
| UX 实践 | `ux` | `--domain ux "animation accessibility"` |
| 备选字体 | `typography` | `--domain typography "elegant luxury"` |
| 落地页结构 | `landing` | `--domain landing "hero social-proof"` |

## Step 4：技术栈实践（默认 html-tailwind）

```bash
python3 uiux-db-scripts/search.py "<keyword>" --stack html-tailwind
```

可用栈：`html-tailwind`, `react`, `nextjs`, `vue`, `svelte`, `swiftui`, `react-native`, `flutter`, `shadcn`, `jetpack-compose`, `astro`, `nuxtjs`, `nuxt-ui`

## 说明

- 数据：67 styles / 96 色板 / 57 字体配对 / 25 图表类型，13 技术栈
- 脚本自定位 `data/`（`Path(__file__).parent.parent`），任意 cwd 可跑
