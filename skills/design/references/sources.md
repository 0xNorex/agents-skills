# 设计站点索引

需要真实参考、可复制源码或动效参数时按需查。每条只写它不可替代的用途；同一控件在别处已有实现时不要重复搜。取原则与做法，不照搬源码。

## 从目标站提 token（比看截图有用）

选好参考站后不要只看图。用浏览器里求值，把它真实的字型、字号阶梯、色值、CSS 变量提出来，写成 `DESIGN.md`：

```js
() => {
  const uniq = (a) => [...new Set(a.filter(Boolean))];
  const els = [...document.querySelectorAll('h1,h2,h3,p,body,a,button')].slice(0, 400);
  const cs = (e) => getComputedStyle(e);
  const vars = new Set();
  for (const s of document.styleSheets) {
    let rules; try { rules = s.cssRules } catch { continue }
    for (const r of rules || []) if (r.style)
      for (const p of r.style) if (p.startsWith('--')) vars.add(p + ':' + r.style.getPropertyValue(p).trim());
  }
  return {
    fonts: uniq(els.map(e => cs(e).fontFamily)).slice(0, 6),
    colors: uniq(els.map(e => cs(e).color + '/' + cs(e).backgroundColor)).slice(0, 12),
    scale: uniq(els.filter(e => /^H[1-3]$|^(P|BODY)$/.test(e.tagName))
      .map(e => { const s = cs(e); return e.tagName + ' ' + s.fontSize + '/' + s.lineHeight + ' w' + s.fontWeight + ' ' + s.letterSpacing })).slice(0, 10),
    vars: [...vars].slice(0, 15),
  };
}
```

- 用 chrome-devtools / Playwright 的 evaluate 跑，或者贴进 console。纯 `curl | grep` 对 JS 渲染站和外部 CSS 经常一无所获。
- 带 hash 的变量名（`--x1mzcagl`）没法直接用，只取它的值：它们是 oklch 或 hex 的色阶。
- 得到的是个案值，不是系统；字阶只取 2–3 级、色取 accent 一两个，多的删。
- 商业字体（Lausanne、Söhne、PP Neue Montreal）不能拷，换 Fontshare 等价品。

想跳过这一步，直接用下面「给 agent 读的参考」里已经导出好的 `DESIGN.md` / MCP。

## 组件源码（copy-paste / shadcn registry）

- [ui.shadcn.com](https://ui.shadcn.com) —— 默认基座与 a11y 语义
- [21st.dev](https://21st.dev) —— 12000+ 社区组件，一条命令装，搜具体控件最快
- [shadcn.io](https://shadcn.io) —— 按组件翻阅 shadcn 用法与变体
- [tailark.com](https://tailark.com) —— 营销区块与整页结构
- [ui.pacekit.dev](https://ui.pacekit.dev) —— 生产级 blocks 与 starter
- [coss.com/ui](https://coss.com/ui) —— Base UI 系现代组件库（换掉 Radix 时）
- [beautifului.dev](https://beautifului.dev) —— AI 界面原语：流式文本、思考态、审批卡、Agent 任务行
- [ui-snippets.com](https://ui-snippets.com) —— 纯 HTML/CSS 片段，无框架项目用

## 动效与微交互

- [transitions.dev](https://transitions.dev) —— 30+ 具体转场：卡片 resize、数字翻转、菜单 origin 感知、成功勾
- [beui.dev](https://beui.dev) —— Motion 动效原语：Dynamic Island、Dock、Morphing Modal
- [rareui.com](https://rareui.com) —— 克制的少见动效，避免撞款
- [reactbits.dev](https://reactbits.dev) —— 200+ 动画与 micro-interaction
- [magicui.design](https://magicui.design) —— 150+ 动效组件
- [animata.design](https://animata.design) —— 出自真实产品，自带 reduced-motion 兜底
- [ui.aceternity.com](https://ui.aceternity.com) —— 视觉冲击强的 hero、渐变、3D
- [motion-primitives.com](https://motion-primitives.com) —— 轻量动画原语
- [animate-ui.com](https://animate-ui.com) —— Radix + Motion 的全动画组件分发
- [motiq.dev](https://motiq.dev) —— 动画 shadcn 组件 + 组装好的完整工作流块
- [motion.dev/ui](https://motion.dev/ui) —— Motion 官方营销区块，hero/定价/bento 可拍平实现
- [easing.dev](https://easing.dev) —— 缓动曲线集合，取参数

## 真实产品参考（非概念稿）

- [refero.design](https://refero.design) —— 按页面类型、流程、UX pattern、UI element 检索截图
- [mobbin.com](https://mobbin.com) —— 40 万+ 移动与 Web 真实截图，流程最全
- [nicelydone.club](https://nicelydone.club) —— 20 万+ SaaS 截图，可搜 App 内文案
- [pageflows.com](https://pageflows.com) —— 录屏式用户流程
- [component.gallery](https://component.gallery) —— 60 组件 × 95 设计系统，查同一控件各家做法
- [uibook.art](https://uibook.art) —— 按 section / 风格 / 行业筛营销页
- [saasframe.io](https://saasframe.io) —— SaaS 真实页面拆解，看信息层级怎么排
- [selectedscreens.com](https://selectedscreens.com) —— 量小但每项带编辑注释，说明「为什么这个决定好」

## 审美校准（定天花板，不是找素材）

- [godly.website](https://godly.website) —— 高完成度站点的天花板，偏技术/暗色/大动效
- [awwwards.com](https://awwwards.com) —— 行业最高线；有 Developer Award 的站可直接扒源码
- [siteinspire.com](https://siteinspire.com) —— 极简编辑风，品味最贵，反花哨
- [a1.gallery](https://a1.gallery) —— 可按技术栈筛（Next.js / Webflow / 带动效），最贴代码落地
- [minimal.gallery](https://minimal.gallery) —— 只收极简，抄起来最不容易翻车
- [httpster.net](https://httpster.net) —— 老牌排版驱动，不追热点
- [land-book.com](https://land-book.com) —— 按行业与页面类型筛，落地页最全
- [lapa.ninja](https://lapa.ninja) —— 标注配色与字体，免费资源多
- [curated.design](https://curated.design)、[landingfolio.com](https://landingfolio.com) —— 手工精选 + 可复制组件
- [saaslandingpage.com](https://saaslandingpage.com) —— SaaS 首屏与定价页模板化
- [darkmodedesign.com](https://darkmodedesign.com) —— 暗色模式专收
- [brutalistwebsites.com](https://brutalistwebsites.com) —— 反精致路线，用对反而更贵
- [uidesigndaily.com](https://uidesigndaily.com) —— 可下载界面素材

## 细节补丁（最容易露怯的两块）

- [footer.design](https://footer.design)、[navbar.gallery](https://navbar.gallery) —— 页脚 / 导航栏各家做法
- [designspells.com](https://designspells.com) —— 只收「小惊喜」交互细节，一页加一个就够

## 给 agent 读的参考（vibecoding 用）

这类站直接把设计系统输出成提示词或结构化文件，比截图省一轮翻译。

- [refero.design/styles](https://refero.design/styles) —— 2000+ 真实产品设计系统，导出 `DESIGN.md` 喂给 Cursor / Claude / v0
- [palatemcp.com](https://palatemcp.com) —— 每站做深度拆解（字号、行高、色值、动效时长），有 MCP 可直连 agent
- [motionsites.dev](https://motionsites.dev) —— 即复即用的建站提示词库

## 字体与配色源

uiux-db 给的是字体配对方案，缺免费可商用字体和真机预览时来这里。

- [fontshare.com](https://fontshare.com) —— 免费可商用高质量字族，替代 Lausanne / Söhne 一类商业字体
- [typewolf.com](https://typewolf.com) —— 看某款字体在真实站点里怎么用
- [realtimecolors.com](https://realtimecolors.com) —— 配色方案套到真实页面布局上看效果

底层原语：[radix-ui.com](https://www.radix-ui.com) · [base-ui.com](https://base-ui.com) · [heroui.com](https://www.heroui.com)

各设计系统的官方文档与安装命令见 [appendix.md](appendix.md)，不在此重复。
