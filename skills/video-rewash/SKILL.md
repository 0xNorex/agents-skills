---
name: video-rewash
description: 电商带货短视频全帧防查重洗稿：替换出镜人物、家居背景、口播文案配音、商业花字与BGM，同时 100% 保留原片产品主体像素不变，双交付 1080p 超清成片与剪映专业版多轨草稿包。当用户说「洗视频」「洗稿这条视频」「换人物和背景重做这条带货视频」时触发；纯文案改写、无AI重绘的普通混剪或单张封面设计不触发。
---

# 电商短视频全帧防查重洗稿 (Video Rewash)

将既有电商种草/带货短视频洗为平台过审的新原创成片：**人物全换 + 背景全换 + 口播声纹全换 + 每秒感知指纹（pHash）全换，且产品主体像素与原片 100% 一模一样。**

核心可复用脚本：`scripts/rewash_kit.py`（相对于本 `SKILL.md` 所在目录解析，运行环境优先用项目 `.venv/bin/python` 或 `uv run`）。

端到端确定性状态机 CLI：`scripts/rewash_pipeline.py`（统一入口，硬锁模型/画幅/帧率/字幕/Prompt，禁止改参）：

```bash
python scripts/rewash_pipeline.py init --src 纯净版.mp4 --work ../rewash_XXX [--with-asr]   # 分镜 + job.json
python scripts/rewash_pipeline.py prep --config ../rewash_XXX/job.json [--approve-credits]  # 切片/背景锚点图/全片统一配音+音色卡/超镜硬门禁/特写/花字
python scripts/rewash_pipeline.py generate --config ../rewash_XXX/job.json                 # 只预览积分，0 提交
python scripts/rewash_pipeline.py generate --config ../rewash_XXX/job.json --approve-credits
python scripts/rewash_pipeline.py pack --config ../rewash_XXX/job.json                     # 成片 + 剪映草稿 + 验收
python scripts/rewash_pipeline.py run --config ../rewash_XXX/job.json [--approve-credits]  # prep -> generate -> pack
```

## 六条红线（违反即返工）

1. **生图只出全局固定资产，严禁逐镜生首帧图（全片唯一主路，不再分模式）**：
   - **为什么严禁逐镜生成首帧图（`pershot_i`）？** 为每个分镜单独跑 `image2image` 生首帧图会导致不同分镜之间的橱柜颜色/比例、人物脸型发生跨镜头漂移。
   - **固定三件套（全片只出这 3 张）**：`head_3view_2k.png` + `fullbody_3view_2k.png`（人物纯白底 2K 三视图，VIP `0` 积分）+ **`bg_anchor_2k.png`（全局唯一 2K 背景锚点图，Maestro VIP `0` 积分）**；**严禁逐镜生成任何首帧图**。
   - **为什么必须锁定单张全局背景锚点图？** 柜体木纹色号/材质光泽/改色边界只能有一个基准，否则每镜各自改色必出跨镜色差与门板造型漂移；`bg_anchor_2k.png` 由原片最广角全景帧（自动取 `ai` 分镜最广角 medoid 帧）经 `dreamina image2image 5.0 2k --ratio=9:16` 一步直出：移除人物并还原其身后柜门/地面，同时把全部白色与浅色木作柜体统一换成同一色号木纹。提示词严禁写“留缝/黑缝”，生图前严禁用 Python 硬抠硬贴垫图。
   - **生成与复用**：一律由 `rewash_pipeline.py prep` 内置的 `_ensure_bg_anchor()` 自动生成到 `<work>/refs/bg_anchor_2k.png`（跨房型时把目标风格参考图配成 `bg_style_ref` 作第二张 `--images` 一并送入）；**已存在则 0 积分复用**；非 `maestro` 档位账号必须显式加 `prep --approve-credits` 才准扣积分生图。
   - **温馨实木色预设池（唯一允许的家装木纹方向，严禁蓝绿高饱和塑料色）**：`warm_cocoa_oak`（侘寂/奶油中古暖可可橡木）、`warm_cherry_teak`（复古樱桃木+缅甸柚木）、`light_warm_oak`（北欧奶油浅暖白橡木，用于原片本身是深色柜体的反差换色）、`vintage_walnut`（温润深色中古黑胡桃木）。`job.json` 的 `bg_anchor_cabinet_desc` 填上述 key、`random` 或留空时，`_ensure_bg_anchor()` 自动展开成「同色号同木纹走向 + 严禁遗漏上方白色顶柜 / 严禁增删柜体或封堵水池台面凹槽」的完整改色描述，并把解析结果持久化进 `<work>/bg_anchor_job.json`（重跑复用同一款，不会换色重抠）；填自定义长描述则原样使用。
   - **上传前置**：`_ascii_assets()` 把 2K `.png` 统一转 `96%` 质量 `.jpg` 落到 `/tmp/rewash_<video_id>/`，防 `4.5MB` PNG 触发 TOS `context deadline exceeded` 上传超时。
2. **每一笔即梦积分必须经用户同意后才能调用（含重跑/补跑/调参），且生视频严禁擅自切模型**：
   - 跑任何消耗积分的 `dreamina` 命令前，必须先算清预估积分并列出待调命令，**严格经用户明确同意后才准执行；任何异常重跑、补跑或改参重提也必须每一笔单独先问过用户，严禁未经同意擅自消耗积分**。
   - **生视频模型与画幅死锁铁律**：`multimodal2video` **只允许使用 `--model_version=seedance2.0mini --video_resolution=720p --ratio=9:16`**（预估 `9~12积分/秒`：4秒=`36~48`积分，5秒=`45~60`积分；加传 `--audio` 实测不额外加收）。**严禁擅自改用 `seedance2.0`、`seedance2.0_vip`、`seedance2.0fast`、`seedance2.0fast_vip` 或 `seedance2.5`！** 遇到单模型并发上限报错（`ret=1310, ExceedConcurrencyLimit`）时，**必须原地等待上一条 `seedance2.0mini` 完成后串行提交，严禁跨模型乱投消耗高额积分！**
3. **全片统一 `VoxCPM`/`IndexTTS` 配音 + 正脸交互镜传固定音色卡自然开口 + 背身/蹲姿标 `silent_action` 闭嘴交互（KISS 零裁剪统一参考）**：
   - **配音唯一音源（全片 100%）**：`prep` 对全片所有分镜（`ai` + `closeup` + `split`）都用同一条 `ref_wav` 经 `IndexTTS-2.5`（失败降级 `VoxCPM`）合成 `voice_XX.wav` 干声，并跑 `_compute_layout()` 不超镜硬门禁。全片只有这一路声源：同一音色、同一语速、零声场跳变；`closeup` 镜也照常配音，不做无声段。
   - **三档入参（由 `_is_speak_ai_seg()` + `_dreamina_cmd()` 自动组装，禁止手工改）**：
     - **正脸交互镜**（`kind=ai` 且非 `no_actor`/`silent_action`）：`--video=sXX.mp4 --audio=timbre_ref.wav --image=bg_anchor.jpg --image=head_3view.jpg --image=body_3view.jpg` + 【KISS 正脸说话模板】。实测加 `--audio` **不额外加收**，统一按 `9~12积分/秒` 预估（与 `CREDITS_PER_SEC_RANGE = (9, 12)` 一致）。
     - **闭嘴家务镜**（侧身弯腰放衣/蹲姿拿鞋等低头专注镜头）：在 `job.json` 标 `"silent_action": true`（`kind=split` 自动归入本档）；**不传 `--audio`**，用【KISS 闭嘴动作模板】。
     - **无人空镜**（`no_actor: true`）：只传 `--video + --image=bg_anchor.jpg`，用【KISS 无人空镜模板】（Prompt 里严禁出现任何人物描述，否则模型会强行留人加戏）。
   - **统一音色卡 `timbre_ref.wav`**：`_stage_ascii_inputs()` 自动把 `ref_wav` 截成 `/tmp/rewash_<video_id>/timbre_ref.wav`（`-ac 1 -ar 44100 -c:a pcm_s16le`），截取上限按本片最长开口镜动态计算 `timbre_cap = round(min(4.80, 14.80 - max_vid_sec), 2)`，硬保证 `video_dur + timbre_dur < 15s` 输入上限；开口镜最长 `> 12.8s`、截取后音色卡 `< 2.0s` 或缺有效 `ref_wav` 一律直接 `SystemExit`，全片无开口镜时清掉 `/tmp` 陈旧音色卡（绝不复用上一片）；全片正脸镜共用同一张卡，音色 100% 一致。
   - **丢弃即梦音轨 + 自动等比收口对齐**：即梦会把「张嘴→换气→合唇微笑」的尾巴一起生成，尾巴比自合成干声长，直接按配音帧数硬切会咬掉尾音。`_finalize_generated()` 对正脸交互镜按 `20ms` 窗扫即梦原生音轨、取 `RMS > 0.015` 的最后一个有声窗结束秒存 `job['native_speech_end_sec']`（写进 `dreamina_jobs.json`）；`pack` 的 `_clip_source()` 再按 `idxs = np.linspace(0, span_frames - 1, nf)` 把整段等比压回本镜配音帧数（仅当 `nf < span_frames <= 1.45*nf` 才收口，否则原样截取 `raw_ai[offset:offset+nf]`，旧工程无该字段 100% 后向兼容）。成片只用 `voice_XX.wav`，即梦音轨只用于测有声区间、不参与混音。
   - **花字防遮挡自适应坐标铁律**：严禁把花字死板固定在 `cy=305` 压住人物额头或五官！凡是**半身近景镜头**（人物头部位于 `y=80..520`），花字必须下置到字幕下方的纯色衣裙安全区（**`cy=1525`**）；凡是**全身远景镜头**（人物头顶低于 `y=380`），花字置于顶部柜体留白区（**`cy=215..305`**，且避开侧站人物发丝）。
   - **严禁针对每个分镜现场编造长篇具体动作描述**（避免文字与 `@video1` 动作控制冲突），一律使用下方【KISS 三档固定模板】；`spoken_line` 由脚本取 `'，'.join(seg['subparts'])`（无 `subparts` 时取 `seg['text']`）自动填充，禁止手写。
4. **8x8 局部网格跳切检测 + 零切点硬门禁 + `纯净版` 零预处理原样直喂（根治跨切点串镜与源头画面抖动）**：
   - HEVC 原片严禁按时间戳随机 `seek` 截取，且**严禁仅用全画幅均值帧差（Global Mean Diff）切分镜头**——全画幅均值帧差会漏检背景 90% 静止的**同机位跳切（Jump Cut，如左小筒塞衣跳切到右小筒关门、远景跳切到中景）**，一旦将含跳切的多镜头片段传给 `multimodal2video`，AI 必出现舱门瞬移反跳或半途机位突变。
   - **`multimodal2video` 输入时长真相与源头防抖铁律**：输入 `--video` 与 `--audio` **原生支持 `2.0~15.0s`**（仅输出参数 `--duration` 下限为 `4s`）！一律调用 `rewash_kit.py` 的 `detect_atomic_shots()` 与 `export_verified_atomic_clip()`：
     - **`>=2.05s` 的镜头 100% 按 `纯净版.mp4` 原帧原速原样直切直喂**，**严禁做 `Palindrome` 正反倒放补尾、严禁 `setpts` 慢放拉长、严禁本地 `vidstab` 二次稳像**（在推拉/摇移镜头尾部拼接倒放回文帧会导致模型学出全片周期性往复抽动抖动！）；
     - 仅当极短单镜 `<2.05s` 时，仅将**最后一帧静态定格（Freeze Last Frame）**补至 `2.05s` 满足 CLI 下限，组装成片时截取前 `valid_frames_24fps` 帧。
   - **全片零裁剪统一参考**：所有分镜 100% 死传同一张 `bg_anchor.jpg`。`bg_anchor_s{idx:02d}.jpg` 的 `cv2.matchTemplate` 同景别自动裁剪已废除（逐镜裁剪会让柜体色号/比例、门板造型跨镜漂移），`_stage_ascii_inputs()` 会顺带清掉 `/tmp` 里的旧裁剪残件。
   - **源切片统一剥音轨**：`_stage_ascii_inputs()` 落 `s{idx:02d}.mp4` 时固定用 `ffmpeg -y -v error -i src -an -c:v copy dst`，杜绝原片残留音轨被模型当成口型依据。
   - **首帧切镜残影**：源切片 `f=0..1` 若带上一镜切镜缩放残影，按 `1.0x` 原速切掉首部 `1~2` 帧（尾部静帧补齐同帧数），防首帧残影导致前 1 秒漏换人。

5. **视频 24fps 1:1 整数帧原速单次直出，禁慢放、禁跨帧混合、禁多余贴面板条**：`seedance2.0mini 720p` 原生为 `24fps`，成片锁定 `24fps` 逐帧映射（100% 原始画幅零裁剪 + `Lanczos4` 超分 + 内存单次流式 `CRF 14` 编码）：**非开口镜（`closeup` / `silent_action` / `no_actor`）严格 `1:1` 原速映射，仅开口镜（`_is_speak_ai_seg()`）允许在 `(1.0, 1.45]` 范围内按 `native_speech_end_sec` 自动等比收口**（把即梦多生成的「张嘴→换气→合唇微笑」尾巴压回本镜配音帧数，绝不慢放拉长）；**严禁用 `cv2.addWeighted` 跨帧线性混合转 30fps（会导致 80% 帧双影发糊），严禁将短片段慢放 >1.1x 拉长（会导致帧率跌至 12fps 卡顿），严禁做多余的 Python 逐帧贴面板条**。
6. **强制 Phase 1 全局基准图肉眼门禁（Gate）**：Phase 1 纯生图产出 3 张全局静态基准图（新演员大头照三视图 + 全身站立三视图 + 全局唯一背景锚点图 `bg_anchor_2k.png`）及分镜配音后，**必须停下请用户肉眼确认无误并批准积分预算后，才准进入 Phase 2 跑付费 `multimodal2video` 视频**。

---

## 标准化固定 Prompt 模板（禁止自由发挥）

生图与生视频的 Prompt 已完全标准化固化，**严禁按每个镜头自由发挥编造冗余动作描述**：

### 1. 【生图模板 1】生成人物纯白底 2K 大头照三视图（`head_3view_2k.png`）
- **输入**：`--image` 新演员清晰正脸照 + 侧脸照
- **固定参数**：`dreamina image2image --model_version=5.0 --resolution_type=2k --ratio=4:3`
- **固定 Prompt**：
  ```text
  参考上传图片中的女性面部特征，生成一张纯白背景（#FFFFFF）的摄影棚超清人物头部三视图设定卡（从左至右依次为：正脸特写、90度正侧面特写、背面发型肩颈特写）。100%还原人物五官骨相、脸型、眉眼鼻唇与真实皮肤纹理毛孔，自然眼神光，去AI磨皮塑料感，2K超高清。
  ```

### 2. 【生图模板 2】生成人物纯白底 2K 全身站立三视图（`fullbody_3view_2k.png`）
- **输入**：`--image` 新演员全身穿搭照 + `head_3view_2k.png`
- **固定参数**：`dreamina image2image --model_version=5.0 --resolution_type=2k --ratio=4:3`
- **固定 Prompt**：
  ```text
  参考上传图片中的女性面部与全身服装穿搭，生成一张纯白背景（#FFFFFF）的摄影棚超清人物全身站立三视图设定卡（从左至右依次为：正面自然站立全身、90度正侧面站立全身、背面站立全身）。双手自然垂放，完整展现头身比例、服装版型材质与鞋子细节，五官与参考图100%一致，2K超高清。
  ```

### 3. 【生图模板 3】生成全局唯一 2K 背景锚点图（`bg_anchor_2k.png`）
- **输入**：`--image` 原视频最广角全景帧 (`@image1`，`rewash_pipeline.py prep` 自动从 `ai` 分镜取最广角 medoid 中间帧落 `<work>/refs/bg_source_wide.png`) + `--image` 跨房型需要的目标风格参考图 (`@image2`，配 `bg_style_ref`，同房型可不传)
- **固定参数**：`dreamina image2image --model_version=5.0 --resolution_type=2k --ratio=9:16`
- **柜体木纹取 4 款温馨实木色池之一**（`bg_anchor_cabinet_desc` 填 key / `random` / 留空，脚本自动展开并落 `<work>/bg_anchor_job.json`）：

| key | 柜面描述 | 适用 |
|---|---|---|
| `warm_cocoa_oak` | 侘寂与奶油中古风的温润烟熏暖可可橡木天然直纹柜面（柔和高级暖灰咖实木纹理、细腻哑光木皮质感） | 默认暖木调 |
| `warm_cherry_teak` | 复古暖调樱桃木与缅甸柚木天然直纹实木柜面（温润暖琥珀棕实木肌理、哑光木蜡油质感） | 复古暖调 |
| `light_warm_oak` | 清爽北欧奶油浅暖白橡木天然直纹实木柜面（明亮温润的原木直纹哑光清漆质感） | 原片本身是深色柜体时做反差换色 |
| `vintage_walnut` | 温润深色中古黑胡桃木天然直纹柜面 | 深色中古风 |

- **固定 Prompt**（`{bg_anchor_cabinet_desc}` 由脚本按上表展开为「将画面中全部白色与浅色木作柜体（…）100%统一替换为同一色号、同一木纹走向的<柜面描述>（严禁遗漏上方白色顶柜，严禁增删柜体或封堵水池台面凹槽，严禁蓝绿高饱和塑料色）」）：
  ```text
  严格保持图1的真实室内空间透视结构、相机焦段景深、水池台面凹槽开口、白色陶瓷洗手盆与水龙头、门板凹凸框线造型、地面地毯、窗帘、绿植小凳与光线完全不变，100%原样保留画面中心家电产品的外观、颜色、紧闭舱门、旋钮与屏幕标识不变；彻底移除画面中的人物并自然还原其身后被遮挡的柜门与地面，不出现任何人物；{bg_anchor_cabinet_desc}，真实室内摄影实拍质感，2K超高清。
  ```
- **产物固定落盘**：`<work>/refs/bg_anchor_2k.png`（原图在 `<work>/refs/bg_anchor_raw/`；已存在则 0 积分复用，严禁重跑）。

### 4. 【生视频模板】KISS 零裁剪三档多模态生视频（`multimodal2video`）
- **固定参数（严禁更改模型或漏传比例）**：`dreamina multimodal2video --model_version=seedance2.0mini --video_resolution=720p --ratio=9:16 --duration=<max(4, ceil(raw_sec))>`
- **全片参考只此一套**：`--image=bg_anchor.jpg` (`@image1`) 全片同一张；人物档再补 `--image=head_3view.jpg` (`@image2`) + `--image=body_3view.jpg` (`@image3`)；正脸档再加 `--audio=timbre_ref.wav` (`@audio1`)。
- **三档由分镜字段自动选，禁止手工拼**：

| 档位 | 判据 | 入参 | Prompt 常量 |
|---|---|---|---|
| 正脸说话 | `kind=ai` 且无 `no_actor`/`silent_action` | `--video --audio=timbre_ref.wav --image×3` | `KISS_SPEAK_PROMPT` |
| 闭嘴动作 | `silent_action: true` 或 `kind=split` | `--video --image×3` | `KISS_SILENT_PROMPT` |
| 无人空镜 | `no_actor: true` | `--video --image=bg_anchor.jpg` | `KISS_NO_ACTOR_PROMPT` |

- **【KISS 正脸说话模板】**（`{spoken_line}` = `'，'.join(seg['subparts'])`，无 `subparts` 时取 `seg['text']`）：
  ```text
  保持 @video1 的机位景深、景别构图、家电外观与手部身体交互动作；不要参考 @video1 的嘴型，人物仅参考 @audio1 的女声音色与语速（严禁复述 @audio1 中的原有词句），用清晰干净的普通话无背景音乐无环境杂音自然同步说出：“{spoken_line}”；将柜体木纹替换为 @image1 的同色实木纹理；将人物替换为 @image2 和 @image3 中的女性，真实实拍质感。
  ```
- **【KISS 闭嘴动作模板】**：
  ```text
  保持 @video1 的机位景深、景别构图、家电外观与肢体动作，不要参考 @video1 的说话嘴部动作，人物不说话；将柜体木纹替换为 @image1 的同色实木纹理；将人物替换为 @image2 和 @image3 中的女性，真实实拍质感。
  ```
- **【KISS 无人空镜模板】**：
  ```text
  参考 @video1 的真实机位、平滑运镜与光学景深，画面保持无人出镜；房间柜体的木纹色号、材质光泽与改色边界100%对齐 @image1（严禁增删柜体或封堵原有水池台面凹槽、严禁改变门板凹凸造型、严禁改变地面地毯窗帘绿植及墙面颜色）；100%保持视频中家电产品的外观、舱门状态与面板细节不变，真实摄影机实拍质感。
  ```

---

## 标准五步工序

### 1. 素材盘点与零串镜分镜
- 优先以目录内无花字底片（如 `纯净版.mp4`）为画面源（若底部带灰底免责条先用 `crop_box` 无损裁除），以 `成品版.mp4` 或文案 `txt` 提取原口播词与卖点节奏。
- 检测切点后将全片镜头归类（`kind` + `no_actor`/`silent_action` 三个字段决定入参档位）：

| 镜头类型 | 处理方式 | 积分成本 |
|---|---|---|
| **正脸口播交互镜**（`kind=ai`） | `纯净版` 原速直切 (`@video1`) + 全片同一张 `bg_anchor.jpg` (`@image1`) + 人物三视图 (`@image2/@image3`) + 统一音色卡 `timbre_ref.wav` (`@audio1`)，调 `multimodal2video --model_version=seedance2.0mini --video_resolution=720p --ratio=9:16` | `9~12积分/秒`（`--audio` 实测不额外加收；4s=`36~48`积分，5s=`45~60`积分） |
| **背身/低头家务镜**（`silent_action: true` 或 `kind=split`） | 同上但不传 `--audio`，人物闭嘴只做肢体交互 | `9~12积分/秒` |
| **无人空镜**（`no_actor: true`） | 只传 `--video` + `--image=bg_anchor.jpg` | `9~12积分/秒` |
| **真机按键微距 / 手持屏幕 / 滚筒水流 / 多列卖点卡**（`kind=closeup`） | 统一调用 `rewash_kit.universal_closeup_rewash()`（`0.0°` 正立零裁边 + 安全区垂直微移 + 方向柔光梯度 + `30→24fps` 映射，`pHash >= 15`） | `0积分` |

- **全局基准资产与生视频标准工序（仅需 1 次多模态分镜/文案规划，零逐镜首帧）**：
  1. **第一步（提纯人物三视图设定卡，VIP `0` 积分）**：套用【生图模板 1】与【生图模板 2】生成 `head_3view_2k.png` 与 `fullbody_3view_2k.png`（同一演员可跨视频直接复用）。
  2. **第二步（全局唯一背景锚点图，Maestro VIP `0` 积分，强制默认）**：一律套用【生图模板 3】生成 `bg_anchor_2k.png`，由 `prep` 内置 `_ensure_bg_anchor()` 自动落到 `<work>/refs/bg_anchor_2k.png`（已存在则 0 积分复用；跨房型只需额外配 `bg_style_ref` 作第二张 `--images`）。
  3. **第三步（全片统一配音 + 统一音色卡）**：按与原片同义等长的洗稿文案，用同一条 `ref_wav` 为**全片每个分镜**（含 `closeup`/`split`）合成 `voice_XX.wav`，切出同一张 `timbre_ref.wav`（`<=4.80s`）。
  4. **第四步（生视频）**：经用户确认全局基准图与积分预算后，调用 `export_verified_atomic_clip()` 导出零预处理纯净原子切片，按分镜字段套用【KISS 三档模板】送入 `multimodal2video`（`--ratio=9:16`）。

### 2. 集中预审并执行即梦生成
- 先运行 `dreamina user_credit` 核对余额与会员档位，向用户展示：**分镜清单 + 每条命令参数 + 预估总积分**，获批后批量提交并轮询落盘至工作目录 `gen_raw/`。
- **上传目录固定 `/tmp/rewash_<video_id>/`**：`prep`/`generate` 每次都会重建（`bg_anchor.jpg` / `head_3view.jpg` / `body_3view.jpg` / `sXX.mp4` / `timbre_ref.wav`），`/tmp` 被清空也能接着跑 `generate`；参考图已转 `96%` JPG、源切片已剥音轨，无需手工处理。
- **CLI 参数与终端链接防坑**：`multimodal2video` 使用单数 `--video`、重复单数 `--image`（正脸档再多传一个 `--audio`）、必填 `--video_resolution=720p` 与 **`--ratio=9:16`**（漏传 `--ratio=9:16` 会默认输出 `16:9` 横屏导致竖屏拉伸变形！）；上传的本地文件路径及向用户输出的 `file:///...` 链接**严禁含中文字符、空格或括号**（一律使用纯英文软链如 `/home/zd/src/ai-mixcut/w567/...` 或 `/tmp/w567/...`，且 `[文件名](file:///...)` 括号内不套反引号，避免终端 OSC-8 超链接被中文截断导致重复显示与点击失效）。

### 3. 1080p 超清分镜重建（通用零裁边微距去重 + 低内存流式合成）
- **低内存流式铁律**：`3.4K/4K HEVC` 源片严禁一次性全片解码进 Python 列表（易超 `20GB` OOM），必须按分镜用 `ffmpeg trim+scale` 提取，成片用 `ffmpeg rawvideo` 管道单次流式写出 `1080x1920@24fps CRF 14`（峰值内存 `<300MB`），严禁使用 `cv2.VideoWriter("mp4v")`。
- **通用实拍微距 / 多列卖点卡零裁边去重**：真机按键微距、滚筒水流、手持分贝计及四列宽幅数据卖点卡统一调用 `rewash_kit.universal_closeup_rewash()`（`0.0°` 正立不歪斜、不裁切边缘列文字、零手工像素坐标，结合安全区垂直微移 + 摄影棚方向性柔光梯度 + `30→24fps` 映射自动步进达标 `pHash >= 15`）。
- **AI 人物/柜体镜原样升频**：`720p` AI 分镜按 `valid_frames_24fps` 逐帧 `Lanczos4` 升至 `1080x1920@24fps`（不做多余的逐帧贴面板条或破坏性后处理）。

### 4. 声音全洗与商业混音
- **首选方案：目标换脸演员本人 `纯净版` 真声零样本克隆（`VoxCPM 2` / `IndexTTS-2`，彻底消除 AI 味，声画同人）**：
  1. **提取快节奏完整句无 BGM 真人参考干声（`~5.8~6.2 字/s` 种草语速）**：从目标演员自己的源片目录（如 `567/纯净版-*.mp4` 正片中段种草句 `5.12s..12.80s`，语速 `6.12 字/s`）切取一段 `6~8s` **语速连贯饱满且完整句结束在静音谷底**的无 BGM 干声（如 `ref_jiajia_brisk_7s65.wav`），附上精确人工校对文本（`prompt_text`），避开开头叹气慢读段，使克隆模型原生继承 `5.5~6.0 字/s` 的紧凑带货语速。
  2. **满密度同义重写（`1s ≈ 5.5~5.8 字`，语音覆盖率 `>=92%`，严禁缩字留空档期）**：先对原片跑分镜 ASR 统计原片真实总字数（通常 35s 视频约 `190~205` 字，即 `5.4~5.8 字/s`），洗稿文案总字数必须与原片保持 `1:1` 等量级（严禁缩减成 `4.0 字/s` 导致句尾出现 `0.8~1.7s` 空白冷场！）。
  3. **免 Key 直调 `openbmb/VoxCPM-Demo`（`VoxCPM 2`）或云端 `IndexTTS-2`**：通过 `uv run --with gradio_client` 调用 `Client("openbmb/VoxCPM-Demo")` 的 `/generate` 接口零样本克隆（数字小数点送 TTS 前写为汉字如 `5.0 -> 五点零`，字幕保留 `5.0`），并逐句跑 `/_run_asr_if_needed` 校验无吞字或尾音幻觉。
  4. **全片只允许一条 `ref_wav` 声源（含 `closeup`/`split` 镜）**：`_synth_missing_voices()` 缺哪句补哪句，绝不混用第二个音色或第二段参考干声，否则跨镜声场跳变必被查重。
  5. **Kaggle 免费 GPU 自托管 `VoxCPM2`（替代 HF Space 排队，`0` 费用）**：`REWASH_TTS_BACKEND=kaggle python scripts/rewash_pipeline.py prep --config ../rewash_XXX/job.json`（或独立跑 `python scripts/rewash_tts_kaggle.py --job ../rewash_XXX/job.json`）。`rewash_tts_kaggle.synth_batch()` 把「`ref_wav` 干声(base64) + 全片台词 + prompt 文本」打进一个 Kaggle script kernel（`ccdsas/rewash-tts-voxcpm2`，`enable_gpu` + `enable_internet`，无需数据集），跑完用 `kaggle kernels output --file-pattern` 只取回 `voice_*.wav`，再走同一套 `_trim_and_fade_voice()` 1.0x 裁静音落盘，产物与 HF Space 版完全同构。可选环境变量：`REWASH_TTS_KERNEL` / `REWASH_TTS_ACCELERATOR`（默认 `NvidiaTeslaT4`）。实测（2×Tesla T4 15GB，`torch 2.11.0+cu130`）：`pip install voxcpm` 35s、模型加载 129s、RTF≈2、峰值 6.0GB、12 句 34s 音频共 72s 生成、单次全流程约 4~6 分钟；周额度 30h，用完即停`kernel`（`kaggle kernels delete` 不影响历史产物）。
  6. **严守 `1.0x` 原速、仅切首尾静音与紧凑气口排轨（句首第 `1` 帧即 `~42ms` 起播、句尾留 `1` 帧，相邻分镜最小静音气口 `2` 帧即 `~83ms`，`0` 重叠）**：仅切除每句 WAV 首尾死静音（`<-38dB`）并加 `12ms/18ms` 淡入淡出，**严禁使用 `stop_periods=-1` 切句中气口，严禁对语音做 `atempo` 加速**；`_voice_frames()` 按 `ceil((voice_dur + 2/FPS) * FPS)` 供帧，`_build_voiceover()` 用 `adelay = (output_start_frame + 1) / FPS * 1000` 让每句在第 `1` 帧起播并同步绑定单行字幕区间，`_assert_zero_overlap()` 再逐窗强制证明相邻分镜 **`0` 重叠**（间隔区峰值 `< 1e-3`）。
- **备选方案：火山引擎「直播一姐」TTS（`BV418_streaming`）**：仅在目标演员无任何历史真声干声素材时回退使用 `rewash_kit.py tts --speaker BV418_streaming`（同样遵守 `speed=10` 原速、禁句中抽气口、禁 `atempo`）。
- **剪映专属 320kbps BGM + 自动闪避**：优先从 `/home/zd/src/ai-mixcut/assets/bgm/剪映专属/`（对照 `剪映目标BGM清单.md` 38 首真乐器曲库）选曲，严禁误用 `87kbps` 旧合成曲；叠加 3~4 处卖点清脆卡点音效（SFX）后调用：
  ```bash
  python scripts/rewash_kit.py mix-audio --vo voiceover.wav --bgm "../assets/bgm/剪映专属/36_轻快愉悦 享受生活.mp3" --sfx sfx.wav --dur 35.333 --out final_mix.m4a
  ```
  自动切去 BGM 片头空白，双声道立体声定标（说话时 BGM `~ -25 dBFS` 清晰铺底不抢词，气口回升至 `~ -21 dBFS`）。

### 5. 商业包装、双交付与量化验收
- **无黑框多变综艺立体花字（强制默认）**：**严禁使用半透明黑框胶囊花字**。一律调用 `rewash_kit.py` 内置的 **12 款无黑框综艺种草立体花字库**（`VARIETY_STYLES`：`model_yellow` 斜切黄条、`burst_orange` 橙字放射线、`arrow_red` 红光飙升箭头、`check_blue` 绿勾冰蓝字、`bubble_aqua` Q弹晶透水珠泡泡、`sparkle_gold` 流金摩卡四角星芒、`lightning_cyan` 闪电电光青机甲字、`shield_emerald` 翡翠十字护盾、`crown_berry` 斜戴小皇冠莓果粉字、`stamp_vermilion` 朱砂实测印章、`split_highlight` 双色碰撞金句、`tech_lime` 得意黑斜体荧光青柠双斜杠，横跨 8 款正版潮流标题字体）：
  1. 用 `pick_variety_styles(texts, seed=N)` 按卖点语义匹配并确保**单条视频内 100% 零重款、跨视频按 `seed` 自动轮换不同组合**；
  2. 用 `render_variety_sticker(style, text, out_png)` 2x 超采样输出透明贴纸；
  3. 用 `overlay_variety_sticker(..., anim_mode=...)` 交替搭配 `jelly_pop` / `tilt_snap` / `slide_spring` / `pulse_pop` 4 种灵动入场动效。
- **字幕与调色（强制美的授权正大黑 + 原片标准 `62px` & `y=1320` + 专有名词视觉核对）**：
  1. **美的商用授权字体锁定**：口播字幕强制使用 `/home/zd/src/ai-mixcut/assets/fonts/midea_fonts/FZZDHJW.TTF`（**方正正大黑简体**，源自 `方正字库80款-美的(1).zip` 美的集团正版商用白名单字库，与美的/小天鹅官方原片成片字幕 100% 同款字体），严禁使用未授权商业字体。
  2. **字号、配色与高度 1:1 对齐美的官方原片标准**：`1080x1920` 画布下字号锁定 **`62px`**（单行像素宽 `<= 960px` 自适应防贴边），纯白字芯 `#FFFFFF` + 纯黑描边 `#101010`（`stroke_width=7px`）；垂直位置锁定 **`y_center = 1320`**（滚筒视窗中央黄金阅读区，剪映草稿对应 `transform_y = -0.375`, `size = 9.5`），**严禁压低到 `y > 1450`** 被抖音底部文案/小黄车遮挡。
  3. **专有名词必看原片成片画面核对（严禁盲信语音 ASR 导致同音错别字）**：Step 2 写稿与出字幕前，**必须抽帧读取原片带字幕成片画面**逐字核对系列名、版本名与行业规范词（如原片画面为 `小乌梅5.0京选轻享版`，语音 ASR 极易误识为同音错字 `倾享版`；滚筒洗衣机须用 `整筒` 而非 `整桶`），确保全片配音与字幕 0 错别字。
  4. **单行短句不重叠 + 清空旧元数据**：每屏严格只显示单行短句（`6~13` 个汉字视觉宽度，随说话节奏切换，严禁双行长句霸屏），相邻字幕帧区间严格不重叠（`ef_i <= sf_{i+1}`），导出时清空容器旧元数据（`-map_metadata -1`）。
- **双格式交付**：
  1. 直投超清成片 `*_1080p超清.mp4`；
  2. `pyJianYingDraft` 导出的 **5 轨**剪映草稿工程及 `.zip` 包（`ScriptFile(1080, 1920, 24, False)` + `append_track(TrackSpec(...))`：主视频轨 + 贴纸轨 + 口播字幕轨 + 口播画外音轨 + BGM 轨；`AudioSegment` 时长取 `min(total_us, mat.duration)`，相邻 `TextSegment` 微秒区间严禁重叠防 `SegmentOverlap` 报错）。
- **必跑端到端验收（未过严禁报完成）**：
  ```bash
  python scripts/rewash_kit.py verify --orig "原片成品.mp4" --new "新成片_1080p超清.mp4" --draft "剪映草稿目录"
  ```
  通过标准：`passed == true`（MD5 已变、全片逐秒 `1fps 64-bit pHash` 汉明距离最小值 `> 12`、音轨平均电平落在 `[-28, -8] dB`、剪映草稿 `missing_files == 0`），并抽帧拼图肉眼终检切点、产品文字与首尾稳定性。
- **配套封面图洗稿（若源目录含封面图）**：
  1. **严禁脱离视频机位凭空生图**（防巨人比例失真），**严禁直接拿原片封面硬换人强套服装冲突姿势**（如穿半身长裙硬套原封面裤装深蹲必出肢体扭曲/多腿畸形），**严禁用程序硬画封面花字**。
  2. **必须从洗稿正片的自然站立人机同框帧抽帧**，经 `dreamina image2image 5.0 2k --ratio=3:4`（`0` 积分）左右自然延展视野重绘得到与正片柜色/站姿 100% 一致的 `2K 无字实拍底图`。
  3. 将 **`[2K 无字实拍底图, 源成品封面参考图]`** 一并送入 `dreamina image2image 5.0 2k`（`0` 积分），**直接由即梦 5.0 参考原商业封面审美原生生成全套立体花字与卖点徽章排版**（标题置于头顶上方空白区不压头发），并对真机区域做对齐保真且抽检确认无接缝与错漏字。
