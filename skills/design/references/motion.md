# Motion skeletons（GSAP pin / Motion reveal）

只在用户需要 pin/scrub/stagger 时读取。下面是需按页面适配的示例，不是必须安装 GSAP + Motion 的要求；普通 sticky/transition 优先原生 CSS。

若需求是真正的滚动固定，验证元素确实固定而非仅入场。示例采用 `start: "top top"`；实际 offset 应考虑导航高度、容器和视口。适配后验证 resize、内容变化、空内容及 reduced-motion，不能把示例直接当作验收通过。

## 中文说法 → 术语

用户通常不会用术语提需求。先认名字，再选实现；不要凭"酷炫/丝滑/高级感"这类形容词开工。

| 用户可能说 | 术语 | 首选实现 |
|---|---|---|
| 往下滚慢慢出现 / 一个接一个冒出来 | reveal on scroll / stagger | IntersectionObserver 或 `animation-timeline: view()` |
| 滚动时图片慢慢动 | parallax | 多层 `translateY` × 各自速度系数 |
| 滚到某处钉住再播 | pinned scroll scrub | `position: sticky` 容器 + 进度映射，见下方 Vanilla |
| 图案被撕开露出内容 | clip-path reveal | `clip-path: inset()` 过渡 |
| 字一个个蹦 / 逐字揭示 | split text + stagger | 拆 span + `overflow:hidden` 遮罩 |
| 乱码解码 | text scramble | rAF 替换未揭示字符 |
| 卡片堆叠 / 叠牌 | sticky card stack | sticky + 绝对定位 + 进度映射 |
| 页面切换元素飞过去 | shared element transition / FLIP | View Transitions API，降级 WAAPI |
| 鼠标过去有磁性 | magnetic / cursor follower | 指针偏移 × 系数，外环用阻尼跟随 |
| 滚很快画面倾斜 | scroll velocity skew | 滚动速度 → `skewY(clamp(...))` |
| 数字滚动 | number counter / odometer | rAF 插值，插值曲线也要非线性 |
| 弹簧感 / QQ 弹弹 | spring | 半隐式欧拉积分，不是 cubic-bezier |
| 磨砂 / 玻璃 | glassmorphism | `backdrop-filter` |
| 颗粒感 / 胶片噪点 | grain / noise | feTurbulence 当背景图 + `steps()` 抖动 |
| 故障效果 | glitch | 复制图层 + `clip-path: inset()` 分条位移 |

## Vanilla 骨架（无 GSAP 时）

下面三段已验证，任何一段都能独立跑。完整可运行示例（共 30 个模式，含参数与缓动取值）：
[references/demos/motion-lab-vol1.html](references/demos/motion-lab-vol1.html)（滚动叙事 14 个）、[references/demos/motion-lab-vol2.html](references/demos/motion-lab-vol2.html)（转场/物理/滤镜 16 个）。它们是参考与取参来源，不是要整段搬进项目。

```js
const damp = (cur, target, s, dt) => cur + (target - cur) * (1 - Math.exp(-s * dt)); // 帧率无关，别用 lerp(a,b,.1)

// 统一的滚动进度：p ∈ [0,1]，重活只在这一处算
function track(wrap, cb) {
  let top = 0, span = 1;
  const measure = () => { top = wrap.getBoundingClientRect().top + scrollY; span = Math.max(1, wrap.offsetHeight - innerHeight); };
  measure(); addEventListener('resize', measure); new ResizeObserver(measure).observe(wrap);
  const loop = () => { cb(Math.min(1, Math.max(0, (scrollY - top) / span))); requestAnimationFrame(loop); };
  requestAnimationFrame(loop);
}
```

Pinned scrub：外层 `height: 100vh + 滚动距离`，内层 `position: sticky; top: 0; height: 100vh`，进度直接映射属性。scrub 一律 `ease: none`，缓动交给手势。

横向劫持：容器高度设为 `100vh + (轨道宽 − 视口宽)`，滚动 1px 等于横移 1px，就不会有卡顿感。

## 参数起点

缓动用 `cubic-bezier(.22,1,.36,1)`（easeOutQuint）起步；`power1.out` 用于常规入场，`power4.out` 用于标题，`back.out` 仅用于按钮弹一下。只动 `transform`/`opacity`。缓动曲线对比与弹簧参数见 vol2 的 13、27 号。


## Sticky-Stack

```tsx
"use client";
import { useRef, useEffect } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useReducedMotion } from "motion/react";

gsap.registerPlugin(ScrollTrigger);

export function StickyStack({ cards }: { cards: React.ReactNode[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (reduce || !ref.current) return;
    const ctx = gsap.context(() => {
      const cardEls = gsap.utils.toArray<HTMLElement>(".stack-card");
      cardEls.forEach((card, i) => {
        if (i === cardEls.length - 1) return;
        ScrollTrigger.create({
          trigger: card,
          start: "top top",
          endTrigger: cardEls[cardEls.length - 1],
          end: "top top",
          pin: true,
          pinSpacing: false,
        });
        gsap.to(card, {
          scale: 0.92,
          opacity: 0.55,
          ease: "none",
          scrollTrigger: {
            trigger: cardEls[i + 1],
            start: "top bottom",
            end: "top top",
            scrub: true,
          },
        });
      });
    }, ref);
    return () => ctx.revert();
  }, [reduce]);

  return (
    <div ref={ref} className="relative">
      {cards.map((card, i) => (
        <div
          key={i}
          className="stack-card sticky top-0 min-h-[100dvh] flex items-center justify-center"
        >
          {card}
        </div>
      ))}
    </div>
  );
}
```

要点：`start: "top top"`，`pin: true`，除最后一张外都 pin；scale/opacity 由**下一张**的 scroll trigger 驱动。

## Horizontal-Pan

```tsx
"use client";
import { useRef, useEffect } from "react";
import { gsap } from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";
import { useReducedMotion } from "motion/react";

gsap.registerPlugin(ScrollTrigger);

export function HorizontalPan({ children }: { children: React.ReactNode }) {
  const wrap = useRef<HTMLDivElement>(null);
  const track = useRef<HTMLDivElement>(null);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (reduce || !wrap.current || !track.current) return;
    const ctx = gsap.context(() => {
      const distance = track.current!.scrollWidth - window.innerWidth;
      gsap.to(track.current, {
        x: -distance,
        ease: "none",
        scrollTrigger: {
          trigger: wrap.current,
          start: "top top",
          end: () => `+=${distance}`,
          pin: true,
          scrub: 1,
          invalidateOnRefresh: true,
        },
      });
    }, wrap);
    return () => ctx.revert();
  }, [reduce]);

  return (
    <section ref={wrap} className="relative overflow-hidden">
      <div ref={track} className="flex h-[100dvh] items-center">
        {children}
      </div>
    </section>
  );
}
```

要点：wrapper pin，inner track 横滑；`end: "+=${distance}"`。

## Scroll-Reveal Stagger（无 pin 时用这个，别上 GSAP）

```tsx
"use client";
import { motion, useReducedMotion } from "motion/react";

export function RevealStagger({ items }: { items: string[] }) {
  const reduce = useReducedMotion();
  return (
    <ul className="grid gap-6">
      {items.map((item, i) => (
        <motion.li
          key={item}
          initial={reduce ? false : { opacity: 0, y: 24 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.3 }}
          transition={{
            duration: 0.6,
            delay: i * 0.06,
            ease: [0.16, 1, 0.3, 1],
          }}
        >
          {item}
        </motion.li>
      ))}
    </ul>
  );
}
```
