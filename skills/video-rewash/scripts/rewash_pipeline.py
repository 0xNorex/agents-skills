#!/usr/bin/env python3
"""电商带货短视频端到端确定性洗稿状态机 CLI（init -> prep -> generate -> pack -> run）。

本脚本把 SKILL.md 的六条红线固化成可复跑的状态机：所有死锁参数集中在下方常量区
（生视频模型/清晰度/画幅、成片画幅帧率、字幕字体字号位置、pHash 硬门禁、
全片统一「VoxCPM 干声 + 正脸交互镜 timbre_ref 音色卡自然开口」KISS Prompt），任何阶段都不允许临时改参。

典型用法：
  python rewash_pipeline.py init --src 纯净版.mp4 --work ../rewash_721 --with-asr
  python rewash_pipeline.py prep --config ../rewash_721/job.json
  python rewash_pipeline.py generate --config ../rewash_721/job.json            # 只预览积分，不提交
  python rewash_pipeline.py generate --config ../rewash_721/job.json --approve-credits
  python rewash_pipeline.py pack --config ../rewash_721/job.json
  python rewash_pipeline.py run --config ../rewash_721/job.json                 # prep -> generate -> pack
"""
from __future__ import annotations

import argparse
import json
import math
import os
import random
import re
import shutil
import subprocess
import sys
import time
import unicodedata
import wave
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from pyJianYingDraft import (
    AudioMaterial,
    AudioSegment,
    ClipSettings,
    DraftFolder,
    TextBorder,
    TextSegment,
    TextStyle,
    TrackSpec,
    TrackType,
    VideoMaterial,
    VideoSegment,
    trange,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rewash_kit as rk  # noqa: E402

# ============================================================================
# 硬锁常量（严禁按镜头/按视频临时改参）
# ============================================================================
MODEL_LOCK = "seedance2.0mini"
RES_LOCK = "720p"
RATIO_LOCK = "9:16"
WIDTH = 1080
HEIGHT = 1920
FPS = 24
SUB_Y = 1320
SUB_FONT_SIZE = 62
PHASH_MIN_GATE = 13
CRF_LOCK = 14
CREDITS_PER_SEC_RANGE = (9, 12)
FONT_PATH = Path("/home/zd/src/ai-mixcut/assets/fonts/midea_fonts/FZZDHJW.TTF")
CLOSEUP_TARGET_PHASH = 16
# 单句配音帧数 = ceil((voice_dur + 2/FPS) * FPS)：句首留 1 帧、句尾留 1 帧气口，绝不跨镜
VOICE_TAIL_FRAMES = 2
SYNTH_ERROR_STREAK_LIMIT = 2
POLL_INTERVAL_SEC = 25.0
SUBMIT_TIMEOUT_SEC = 300
QUERY_TIMEOUT_SEC = 60

DEFAULT_ACTOR_DESC = "五官、深棕色自然披肩直发与全身服装一致，无原片残留发束"

# 温馨实木色预设池：4 款温馨有质感的家装天然木纹（严禁蓝绿高饱和塑料色）。
# job.json 里 bg_anchor_cabinet_desc 可填下面的 key / 'random' / 留空，_ensure_bg_anchor 自动展开成完整改色描述。
_WARM_CABINET_SCOPE = (
    "将画面中全部白色与浅色木作柜体（包含中心家电正上方的双开顶柜、家电左右包边立柱以及两侧上下柜体与开放格）"
    "100%统一替换为同一色号、同一木纹走向的{wood}（严禁遗漏上方白色顶柜，严禁增删柜体或封堵水池台面凹槽，"
    "严禁蓝绿高饱和塑料色）"
)
WARM_CABINET_PALETTES = {
    "warm_cocoa_oak": _WARM_CABINET_SCOPE.format(
        wood="侘寂与奶油中古风的温润烟熏暖可可橡木天然直纹柜面（柔和高级暖灰咖实木纹理、细腻哑光木皮质感）"
    ),
    "warm_cherry_teak": _WARM_CABINET_SCOPE.format(
        wood="复古暖调樱桃木与缅甸柚木天然直纹实木柜面（温润暖琥珀棕实木肌理、哑光木蜡油质感）"
    ),
    "light_warm_oak": _WARM_CABINET_SCOPE.format(
        wood="清爽北欧奶油浅暖白橡木天然直纹实木柜面（明亮温润的原木直纹哑光清漆质感，适合原片本身是深色柜体的反差换色）"
    ),
    "vintage_walnut": _WARM_CABINET_SCOPE.format(
        wood="温润深色中古黑胡桃木天然直纹柜面"
    ),
}

# 全片统一 KISS 生视频模板（零裁剪：一张全局 bg_anchor + 一张统一音色卡，全片 100% 同一套参考）。
# @video1 = 原速源切片，@image1 = bg_anchor.jpg，@image2/@image3 = 人物三视图，@audio1 = timbre_ref.wav。
# 正脸交互镜（kind=ai）：传 --audio=timbre_ref.wav 让模型只借音色/语速自然开口，口型不跟 @video1。
KISS_SPEAK_PROMPT = (
    "保持 @video1 的机位景深、景别构图、家电外观与手部身体交互动作；不要参考 @video1 的嘴型，"
    "人物仅参考 @audio1 的女声音色（严禁复述 @audio1 原有词句），口型轻柔克制、如日常聊天般微张嘴自然说出：“{spoken_line}”（严禁夸张大张嘴）；"
    "将背景护墙板与柜体木纹替换为 @image1 的同色实木纹理；将人物替换为 @image2 和 @image3 中的女性（{actor_desc}），真实实拍质感。"
)
# 低头专注做家务镜（silent_action / kind=split）：不传 --audio，人物闭嘴只做肢体交互。
KISS_SILENT_PROMPT = (
    "保持 @video1 的机位景深、景别构图、家电外观与肢体动作，不要参考 @video1 的说话嘴部动作，人物不说话；"
    "将背景护墙板与柜体木纹替换为 @image1 的同色实木纹理；将人物替换为 @image2 和 @image3 中的女性（{actor_desc}），真实实拍质感。"
)
# 无人纯空镜变体：只传 @video1 + @image1，提示词严禁出现人物描述（否则模型会强行留人加戏）。
KISS_NO_ACTOR_PROMPT = (
    "保持 @video1 的机位景深、平滑运镜与光学景深，画面保持无人出镜；"
    "将背景护墙板与柜体的木纹色号、材质光泽100%替换为 @image1 的同色实木纹理（保持原有家具沙发茶几地毯窗帘与装饰物不变）；"
    "100%保持视频中家电产品的外观与面板细节不变，真实实拍质感。"
)
# prep 生成的全局唯一 2K 背景锚点图（bg_anchor_2k.png）：图1 = 原片最广角全景帧，移除人物并统一柜体木纹。
BG_ANCHOR_I2I_PROMPT = (
    "严格保持图1的真实室内空间透视结构、相机焦段景深、水池台面凹槽开口、白色陶瓷洗手盆与水龙头、"
    "门板凹凸框线造型、地面地毯、窗帘、绿植小凳与光线完全不变，"
    "100%原样保留画面中心家电产品的外观、颜色、紧闭舱门、旋钮与屏幕标识不变；"
    "彻底移除画面中的人物并自然还原其身后被遮挡的柜门与地面，不出现任何人物；"
    "{bg_anchor_cabinet_desc}，真实室内摄影实拍质感，2K超高清。"
)

SEGMENT_KINDS = ("ai", "closeup", "split")
IMAGE_KEYS = ("bg_anchor", "head_3view", "body_3view")
BG_ANCHOR_POLL_SEC = 300.0


# ============================================================================
# 配置 / 路径 / 通用小工具
# ============================================================================
def _load_json(path: str | Path, default=None):
    p = Path(path)
    if not p.is_file():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def _dump_json(path: str | Path, obj) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_config(path: str | Path) -> dict:
    cfg = _load_json(path)
    if cfg is None:
        raise SystemExit(f"配置文件不存在: {path}")
    missing = [k for k in ("video_id", "src_video", "work_dir", "segments") if not cfg.get(k)]
    if missing:
        raise SystemExit(f"配置缺少必填字段 {missing}: {path}")
    return cfg


def _work(cfg: dict) -> Path:
    return Path(cfg["work_dir"])


def _ascii_dir(cfg: dict) -> Path:
    """dreamina CLI 上传路径严禁中文/空格/括号：统一落纯 ASCII 软目录 /tmp/rewash_<video_id>。"""
    return Path("/tmp") / f"rewash_{cfg['video_id']}"


def _ref_source(cfg: dict, key: str) -> Path | None:
    """参考图源路径：bg_anchor 未显式指定时回落到 prep 生成的全局背景锚点图。"""
    raw = cfg.get(key)
    if not raw and key == "bg_anchor":
        raw = str(_work(cfg) / "refs" / "bg_anchor_2k.png")
    return Path(raw) if raw else None


def _ascii_assets(cfg: dict) -> dict[str, Path]:
    adir = _ascii_dir(cfg)
    out = {}
    for key in IMAGE_KEYS:
        src = _ref_source(cfg, key)
        if src is not None:
            # 统一转存高质量 JPG 上传，把 4MB+ 2K PNG 压至 ~350KB 防国内上传超时
            ext = ".jpg" if src.suffix.lower() == ".png" else src.suffix.lower()
            out[key] = adir / f"{key}{ext}"
    return out


def _stage_ascii_inputs(cfg: dict) -> dict[str, Path]:
    """prep 与 generate 都必须调用：把 bg_anchor/人物三视图/源切片重新落到 /tmp，/tmp 被清空也能续跑 generate。

    音色卡按本片最长开口镜动态截取，硬保证 `video_dur + timbre_dur < 15.0s`；全片无开口镜时清掉 /tmp
    里的陈旧音色卡，绝不复用上一片的缓存。
    """
    adir = _ascii_dir(cfg)
    adir.mkdir(parents=True, exist_ok=True)
    staged = {}
    for key, dst in _ascii_assets(cfg).items():
        src = _ref_source(cfg, key)
        if src is None or not src.is_file():
            raise SystemExit(
                f"缺少参考图 {key}: {src}（bg_anchor 由 prep 生成到 {_work(cfg) / 'refs' / 'bg_anchor_2k.png'}）"
            )
        if src.suffix.lower() == ".png" and dst.suffix.lower() == ".jpg":
            im_bgr = cv2.imread(str(src))
            if im_bgr is None:
                raise SystemExit(f"无法读取参考图: {src}")
            cv2.imwrite(str(dst), im_bgr, [cv2.IMWRITE_JPEG_QUALITY, 96])
        else:
            shutil.copyfile(src, dst)
        staged[key] = dst
    work = _work(cfg)

    # 全片 100% 死传同一张 bg_anchor.jpg：清掠旧版同景别裁剪图，防 /tmp 残留使不同分镜参考图漂移
    for stale in adir.glob("bg_anchor_s*.jpg"):
        stale.unlink()

    for seg in cfg["segments"]:
        if seg["kind"] not in ("ai", "split"):
            continue
        idx = seg["shot_index"]
        src = work / "src_clips" / f"s{idx:02d}.mp4"
        if not src.is_file():
            raise SystemExit(f"Shot {idx} 缺源切片，先跑 prep: {src}")
        dst = adir / f"s{idx:02d}.mp4"
        # 视频流直拷且 -an 显式剥除原片音轨：模型只按画面学动作，配音全片统一走 voice_XX.wav
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(src), "-an", "-c:v", "copy", str(dst)], check=True)
        staged[f"s{idx:02d}"] = dst

    # 统一音色卡 timbre_ref.wav：按本片最长开口镜动态截取，硬保证 video_dur + timbre_dur < 15.0s
    timbre = adir / "timbre_ref.wav"
    speak_segs = [s for s in cfg["segments"] if _is_speak_ai_seg(s)]
    if not speak_segs:
        # 全片无开口镜：音色卡不参与生成，清掉 /tmp 残留，绝不复用上一片的音色
        if timbre.exists():
            timbre.unlink()
        return staged
    ref_wav = cfg.get("ref_wav")
    if not ref_wav or not Path(ref_wav).is_file():
        raise SystemExit(f"存在开口人物镜但未配置有效 ref_wav: {ref_wav!r}")
    max_vid_sec = max(
        _probe_duration(work / "src_clips" / f"s{s['shot_index']:02d}.mp4") for s in speak_segs
    )
    if max_vid_sec > 12.8:
        raise SystemExit(
            f"开口镜最长 {max_vid_sec:.2f}s 超过 Seedance 2.0 音视频合计 15s 上限（需留 >=2.0s 音色卡）"
        )
    timbre_cap = round(min(4.80, 14.80 - max_vid_sec), 2)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(ref_wav),
         "-af", f"atrim=0:{timbre_cap:.2f}", "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(timbre)],
        check=True,
    )
    timbre_dur = _probe_duration(timbre)
    if timbre_dur < 2.0:
        ref_dur = _probe_duration(ref_wav)
        if ref_dur < 2.0:
            raise SystemExit(f"ref_wav 仅 {ref_dur:.2f}s，开口镜音色卡至少需 >= 2.0s 连续参考干声: {ref_wav}")
        raise SystemExit(
            f"音色卡截取后仅 {timbre_dur:.2f}s（timbre_cap={timbre_cap:.2f}s，最长开口镜 {max_vid_sec:.2f}s），"
            f"请提供 >= 2.0s 参考干声: {ref_wav}"
        )
    staged["timbre_ref"] = timbre
    return staged


def _is_speak_ai_seg(seg: dict) -> bool:
    """正脸/半身/全身口播交互镜：传 timbre_ref.wav 让模型借音色自然开口（默认开口镜）。"""
    return seg.get("kind") == "ai" and not seg.get("no_actor") and not seg.get("silent_action")


def _is_silent_seg(seg: dict) -> bool:
    """侧身弯腰放衣/蹲姿拿鞋等低头专注做家务镜：不传 --audio，只学肢体动作。"""
    return bool(seg.get("silent_action")) or seg.get("kind") == "split"


def _spoken_line(seg: dict) -> str:
    return "，".join(seg["subparts"]) if seg.get("subparts") else seg["text"]


def build_prompt(cfg: dict, seg: dict) -> str:
    if seg.get("no_actor"):
        return KISS_NO_ACTOR_PROMPT
    actor_desc = cfg.get("actor_desc") or DEFAULT_ACTOR_DESC
    if _is_silent_seg(seg):
        return KISS_SILENT_PROMPT.format(actor_desc=actor_desc)
    return KISS_SPEAK_PROMPT.format(spoken_line=_spoken_line(seg), actor_desc=actor_desc)


def _probe_duration(path: str | Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        text=True,
    ).strip()
    return float(out)


def _probe_fps(path: str | Path) -> float:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(path)],
        text=True,
    ).strip().splitlines()[0]
    num, _, den = out.partition("/")
    return float(num) / float(den or 1)


def _clip_frame_count(path: str | Path) -> int:
    cap = cv2.VideoCapture(str(path))
    n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    cap.release()
    return n


def _read_frames(mp4_path: str | Path, n_frames: int | None = None) -> list[np.ndarray]:
    """按 1080x1920 Lanczos 逐帧读入 BGR 帧；n_frames=None 时读全部帧。"""
    cmd = ["ffmpeg", "-v", "error", "-i", str(mp4_path), "-vf", f"scale={WIDTH}:{HEIGHT}:flags=lanczos"]
    if n_frames is not None:
        cmd += ["-frames:v", str(n_frames)]
    cmd += ["-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    raw = subprocess.check_output(cmd)
    fb = WIDTH * HEIGHT * 3
    got = len(raw) // fb
    if n_frames is not None:
        assert got == n_frames, f"{mp4_path}: 期望 {n_frames} 帧，实际 {got} 帧"
    return [np.frombuffer(raw[k * fb:(k + 1) * fb], dtype=np.uint8).reshape((HEIGHT, WIDTH, 3)).copy() for k in range(got)]


def _voice_frames(voice_dur: float) -> int:
    return int(math.ceil((voice_dur + VOICE_TAIL_FRAMES / FPS) * FPS))


# ============================================================================
# init：分镜检测 + 可选原片 ASR + job.json 模板
# ============================================================================
def _write_contact_sheet(src: str | Path, shots: list[dict], out_jpg: str | Path, cols: int = 6) -> Path:
    picks = [(s["shot_index"], (s["raw_start_frame"] + s["raw_end_frame"]) // 2) for s in shots]
    buckets = rk.decode_clip_sequential(str(src), [(f"f{idx}", f, f + 1) for idx, f in picks])
    thumbs = []
    for idx, _ in picks:
        frame = buckets[f"f{idx}"][0]
        small = cv2.resize(frame, (216, 384), interpolation=cv2.INTER_AREA)
        cv2.rectangle(small, (0, 0), (78, 40), (0, 0, 0), -1)
        cv2.putText(small, f"#{idx}", (8, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        thumbs.append(small)
    rows = int(math.ceil(len(thumbs) / cols))
    sheet = np.full((rows * 384, cols * 216, 3), 245, dtype=np.uint8)
    for k, thumb in enumerate(thumbs):
        r, c = divmod(k, cols)
        sheet[r * 384:(r + 1) * 384, c * 216:(c + 1) * 216] = thumb
    out_jpg = Path(out_jpg)
    out_jpg.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_jpg), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return out_jpg


def _shot_audio_wav(src: str | Path, fps: float, start_frame: int, end_frame: int, out_wav: Path) -> Path:
    start = start_frame / fps
    dur = (end_frame - start_frame + 1) / fps
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{start:.6f}", "-i", str(src), "-t", f"{dur:.6f}",
         "-vn", "-ac", "1", "-ar", "16000", str(out_wav)],
        check=True,
    )
    return out_wav


def cmd_init(args) -> int:
    work = Path(args.work)
    work.mkdir(parents=True, exist_ok=True)
    src = Path(args.src)
    video_id = args.video_id or work.name
    shots = rk.detect_atomic_shots(src)
    if not shots:
        raise SystemExit(f"分镜检测为空: {src}")
    _dump_json(work / "shots.json", shots)
    sheet = _write_contact_sheet(src, shots, work / "shots_contact.jpg")
    print(f"[init] {len(shots)} 个原子镜头 -> {work / 'shots.json'} / {sheet}")

    if args.with_asr:
        from gradio_client import Client

        client = Client("openbmb/VoxCPM-Demo")
        fps = _probe_fps(src)
        adir = Path("/tmp") / f"rewash_{video_id}"
        adir.mkdir(parents=True, exist_ok=True)
        asr = {}
        for sh in shots:
            idx = sh["shot_index"]
            wav = _shot_audio_wav(src, fps, sh["safe_start_frame"], sh["safe_end_frame"], adir / f"asr_s{idx:02d}.wav")
            text = rk._read_back_asr(client, wav)
            asr[str(idx)] = {"text": text, "wav": str(wav)}
            print(f"[init] ASR shot {idx}: {text}")
        _dump_json(work / "orig_asr.json", asr)

    job = {
        "video_id": video_id,
        "src_video": str(src.resolve()),
        "work_dir": str(work.resolve()),
        "actor_desc": DEFAULT_ACTOR_DESC,
        "head_3view": args.head_3v,
        "body_3view": args.body_3v,
        "bg_anchor": None,
        "bg_style_ref": None,
        "ref_wav": args.ref_wav,
        "bgm": args.bgm,
        "stickers": [],
        "segments": [
            {
                "shot_index": sh["shot_index"],
                "kind": "ai",
                "text": "",
                "subparts": [],
                "split_y": None,
            }
            for sh in shots
        ],
    }
    job_path = work / "job.json"
    _dump_json(job_path, job)
    print(f"[init] job.json 模板 -> {job_path}（按 shots_contact.jpg 填 kind/text/subparts）")
    return 0


# ============================================================================
# 分镜 / 配音帧预算 / 字幕校验
# ============================================================================
def _load_shots(cfg: dict) -> list[dict]:
    work = _work(cfg)
    shots = _load_json(work / "shots.json")
    if shots is None:
        shots = rk.detect_atomic_shots(cfg["src_video"])
        _dump_json(work / "shots.json", shots)
        _write_contact_sheet(cfg["src_video"], shots, work / "shots_contact.jpg")
    return shots


def _max_frames_by_shot(cfg: dict, shots: list[dict], exported: dict) -> dict[int, int]:
    """单镜可用帧预算 = 导出片段的 valid_frames_24fps（无导出记录时按安全帧数折算）。"""
    fps = _probe_fps(cfg["src_video"])
    budget = {}
    for sh in shots:
        idx = sh["shot_index"]
        rec = exported.get(str(idx))
        if rec:
            budget[idx] = int(rec["valid_frames_24fps"])
        else:
            n = sh["safe_end_frame"] - sh["safe_start_frame"] + 1
            budget[idx] = int(round(n * FPS / fps))
    return budget


def _validate_subtitles(segments: list[dict]) -> None:
    for seg in segments:
        idx = seg.get("shot_index")
        if seg.get("kind") not in SEGMENT_KINDS:
            raise SystemExit(f"Shot {idx} kind 非法: {seg.get('kind')!r}（仅 {SEGMENT_KINDS}）")
        text = seg.get("text") or ""
        subparts = seg.get("subparts") or []
        if not text or not subparts:
            raise SystemExit(f"Shot {idx} 缺少 text/subparts，先按 job.json 填稿")
        if "".join(subparts) != text:
            raise SystemExit(f"Shot {idx} subparts 拼接不一致: {''.join(subparts)!r} != {text!r}")
        for part in subparts:
            bad = [ch for ch in part if unicodedata.category(ch).startswith("P") or ch.isspace()]
            if bad:
                raise SystemExit(f"Shot {idx} 字幕含标点/空白 {bad}: {part!r}（字幕正文严禁标点）")
        if seg["kind"] == "split" and not seg.get("split_y"):
            raise SystemExit(f"Shot {idx} kind=split 必须给 split_y（上下分屏分界行）")


def _voice_provider_map(work: Path) -> dict[int, str]:
    report = _load_json(work / "voice_clone_report.json", [])
    out = {}
    if isinstance(report, list):
        for rec in report:
            if "shot_index" in rec and rec.get("provider"):
                out[int(rec["shot_index"])] = rec["provider"]
    return out


def _voice_durations(cfg: dict) -> dict[int, float]:
    work = _work(cfg)
    durations = {}
    for seg in cfg["segments"]:
        wav = work / "voice_clone" / f"voice_{seg['shot_index']:02d}.wav"
        if not wav.is_file():
            raise SystemExit(f"Shot {seg['shot_index']} 缺少配音 {wav}，先跑 prep")
        durations[seg["shot_index"]] = _probe_duration(wav)
    return durations


def _compute_layout(cfg: dict) -> dict:
    """全片帧布局 + 字幕/花字时间轴；任一句配音超出本镜可用帧数立即硬停（不花一分积分）。"""
    work = _work(cfg)
    shots = _load_shots(cfg)
    exported = _load_json(work / "exported_clips.json", {})
    budget = _max_frames_by_shot(cfg, shots, exported)
    durations = _voice_durations(cfg)
    providers = _voice_provider_map(work)

    rows = []
    cur = 0
    for seg in cfg["segments"]:
        idx = seg["shot_index"]
        dur = durations[idx]
        frames = _voice_frames(dur)
        valid = budget[idx]
        assert frames <= valid, (
            f"HARD GATE: Shot {idx} 配音 {dur:.3f}s 需要 {frames} 帧 > 本镜可用 {valid} 帧；"
            f"先把这句稿子改短，严禁超镜（会造成音画错位/吞句）"
        )
        raw_off = seg.get("ai_frame_offset")
        if raw_off is None:
            ai_off = 0
        elif isinstance(raw_off, bool) or not isinstance(raw_off, int) or raw_off < 0:
            raise SystemExit(f"Shot {idx} ai_frame_offset 必须为非负整数: {raw_off!r}")
        else:
            ai_off = raw_off
        if ai_off > 0 and seg["kind"] == "closeup":
            raise SystemExit(f"Shot {idx} kind=closeup 不支持 ai_frame_offset={ai_off}")
        if seg["kind"] in ("ai", "split"):
            ret_clip = work / "gen_retimed" / f"s{idx:02d}_24fps.mp4"
            avail_ai = _clip_frame_count(ret_clip) if ret_clip.is_file() else max(valid, max(4, int(math.ceil(valid / FPS))) * FPS)
            if ai_off + frames > avail_ai:
                raise SystemExit(
                    f"HARD GATE: Shot {idx} ai_frame_offset({ai_off}) + frames({frames}) = {ai_off + frames} > 可用生成帧 {avail_ai}"
                )
        obox = seg.get("overlay_orig_box")
        if obox is not None:
            if (
                not isinstance(obox, (list, tuple))
                or len(obox) != 4
                or any(isinstance(v, bool) or not isinstance(v, int) for v in obox)
            ):
                raise SystemExit(f"Shot {idx} overlay_orig_box 必须为 4 个整数 [x0,y0,x1,y1]: {obox!r}")
            ox0, oy0, ox1, oy1 = obox
            if not (0 <= ox0 < ox1 <= WIDTH and 0 <= oy0 < oy1 <= HEIGHT):
                raise SystemExit(
                    f"Shot {idx} overlay_orig_box 越界 [0..{WIDTH}, 0..{HEIGHT}]: {obox!r}"
                )
            obox = [ox0, oy0, ox1, oy1]
        rows.append({
            "index": idx,
            "kind": seg["kind"],
            "text": seg["text"],
            "provider": providers.get(idx, "existing"),
            "voice": str(work / "voice_clone" / f"voice_{idx:02d}.wav"),
            "voice_duration": round(dur, 4),
            "frames": frames,
            "valid_frames_24fps": valid,
            "output_start_frame": cur,
            "subparts": seg["subparts"],
            "split_y": seg.get("split_y"),
            "recolor_navy_sleeve": bool(seg.get("recolor_navy_sleeve")),
            "ai_frame_offset": ai_off,
            "overlay_orig_box": obox,
            "silent_action": bool(seg.get("silent_action")),
            "no_actor": bool(seg.get("no_actor")),
        })
        cur += frames

    stickers = _sticker_schedule(cfg, rows)
    total_frames = cur
    return {
        "rows": rows,
        "stickers": stickers,
        "duration_frames": total_frames,
        "duration_sec": round(total_frames / FPS, 4),
    }


def _sticker_schedule(cfg: dict, rows: list[dict]) -> list[dict]:
    by_idx = {r["index"]: r for r in rows}
    plan = []
    seen_styles: set[str] = set()
    for st in cfg.get("stickers") or []:
        idx = int(st["segment"])
        if idx not in by_idx:
            raise SystemExit(f"花字 {st.get('key')} 指向不存在的分镜 {idx}")
        row = by_idx[idx]
        style = st.get("style") or "burst_orange"
        if style in seen_styles:
            raise SystemExit(f"单条视频内花字款式 100% 零重款：{style} 重复出现")
        seen_styles.add(style)
        st_s = round(row["output_start_frame"] / FPS + 0.12, 2)
        st_e = round(min((row["output_start_frame"] + row["frames"] - 2) / FPS, st_s + 2.6), 2)
        if st_e <= st_s:
            raise SystemExit(f"花字 {st.get('key')} 时间窗无效: {st_s}~{st_e}")
        plan.append({
            "key": st["key"],
            "text": st["text"],
            "style": style,
            "segment": idx,
            "start_sec": st_s,
            "end_sec": st_e,
            "cx": int(st["cx"]),
            "cy": int(st["cy"]),
            "png": str(_work(cfg) / "stickers_final" / f"{st['key']}.png"),
        })
    return plan


def _write_plan(cfg: dict, layout: dict) -> Path:
    work = _work(cfg)
    plan_path = work / "dense_montage" / "plan.json"
    _dump_json(plan_path, {
        "video_id": cfg["video_id"],
        "new_count": sum(len(r["text"]) for r in layout["rows"]),
        "duration_frames": layout["duration_frames"],
        "duration_sec": layout["duration_sec"],
        "bgm": cfg.get("bgm"),
        "segments": layout["rows"],
        "stickers": layout["stickers"],
    })
    return plan_path


# ============================================================================
# prep：切片导出 / 配音合成 / 帧预算硬门禁 / 特写去重 / 花字
# ============================================================================
def _is_quota_error(err: str) -> bool:
    lowered = err.lower()
    return any(k in lowered for k in ("zerogpu", "quota", "gpu limit", "exceeded your gpu"))


def _synth_missing_voices(cfg: dict) -> None:
    work = _work(cfg)
    voice_dir = work / "voice_clone"
    voice_dir.mkdir(parents=True, exist_ok=True)
    missing = [s for s in cfg["segments"] if not (voice_dir / f"voice_{s['shot_index']:02d}.wav").is_file()]
    if not missing:
        print("[prep] 配音全部就位，跳过合成")
        return
    ref_wav = cfg.get("ref_wav")
    if not ref_wav or not Path(ref_wav).is_file():
        raise SystemExit("缺少目标演员参考干声 ref_wav，无法做真声克隆")

    backend = os.environ.get("REWASH_TTS_BACKEND", "kaggle").strip().lower()
    recs = None
    if backend in ("kaggle", "gpu"):
        # 自托管 VoxCPM2：整批台词打进一个 Kaggle script kernel（base64 内嵌 ref 干声），
        # 跑完只取回 voice_*.wav 再 1.0x 裁静音落盘；绕开 HF Space ZeroGPU 排队/额度。
        from rewash_tts_kaggle import synth_batch

        try:
            recs = synth_batch(
                missing, ref_wav, cfg.get("ref_prompt_text", ""), voice_dir,
                job_name=cfg["video_id"],
                kernel_id=os.environ.get("REWASH_TTS_KERNEL", "ccdsas/rewash-tts-voxcpm2"),
                accelerator=os.environ.get("REWASH_TTS_ACCELERATOR", "NvidiaTeslaT4"),
            )
        except SystemExit as e:
            if os.environ.get("REWASH_TTS_BACKEND"):
                raise
            print(f"[prep] Kaggle GPU 不可用（{str(e)[:140]}）-> 回退 HF Space")
            backend = "space"
    if recs is not None:
        done = {r["shot_index"] for r in recs}
        lost = [s["shot_index"] for s in missing if s["shot_index"] not in done]
        if lost:
            raise SystemExit(f"Kaggle 配音缺失分镜: {lost}")
        prev = [r for r in (_load_json(work / "voice_clone_report.json", []) or [])
                if r.get("shot_index") not in done]
        prev += [{"shot_index": r["shot_index"], "provider": r["provider"],
                  "duration_sec": r["duration_sec"], "wav_path": r["wav_path"]} for r in recs]
        _dump_json(work / "voice_clone_report.json", prev)
    else:
        from gradio_client import Client

        idx_client = Client("IndexTeam/IndexTTS-2.5-Demo")
        vox_client = Client("openbmb/VoxCPM-Demo")
        provider = "IndexTTS-2.5-Demo"
        for seg in missing:
            idx = seg["shot_index"]
            out_wav = voice_dir / f"voice_{idx:02d}.wav"
            t0 = time.monotonic()
            while True:
                try:
                    if provider == "IndexTTS-2.5-Demo":
                        rec = rk.indextts_clone_segment(seg["text"], ref_wav, out_wav, client=idx_client, asr_client=vox_client)
                    else:
                        rec = rk.voxcpm_clone_segment(
                            seg["text"], ref_wav,
                            ref_prompt_text=cfg.get("ref_prompt_text"),
                            out_wav_path=out_wav,
                            client=vox_client,
                            fallback_indextts=False,
                        )
                    break
                except Exception as e:  # noqa: BLE001 - 免费容器额度/排队或连续 2 次同错立即降级 VoxCPM
                    err = f"{type(e).__name__}: {e}"
                    if provider == "IndexTTS-2.5-Demo":
                        print(f"[prep] IndexTTS 不可用（{err[:140]}）-> 自动切换 VoxCPM 原生 1.0x 克隆")
                        provider = "VoxCPM-Demo"
                        continue
                    raise
            print(f"[prep] voice_{idx:02d}.wav <- {rec['provider']} {rec['duration_sec']}s ({time.monotonic() - t0:.1f}s)")

    shots_list = _load_shots(cfg)
    exported = _load_json(work / "exported_clips.json", {})
    budget = _max_frames_by_shot(cfg, shots_list, exported)
    providers = _voice_provider_map(work)
    report = []
    for seg in cfg["segments"]:
        idx = seg["shot_index"]
        wav = voice_dir / f"voice_{idx:02d}.wav"
        dur = _probe_duration(wav)
        report.append({
            "shot_index": idx,
            "text": seg["text"],
            "wav_path": str(wav),
            "duration_sec": round(dur, 3),
            "provider": providers.get(idx, "existing"),
            "max_frames_24fps": budget[idx],
            "max_sec_24fps": round(budget[idx] / FPS, 3),
        })
    _dump_json(work / "voice_clone_report.json", report)


_ORIG_1FPS_CACHE: dict[str, list[np.ndarray]] = {}


def _orig_1fps_frames(src: str | Path) -> list[np.ndarray]:
    """全片 1fps 原帧（时间轴重排后，pHash 只能以「最近邻原帧」为有效门槛）。"""
    key = str(Path(src).resolve())
    if key not in _ORIG_1FPS_CACHE:
        cap = cv2.VideoCapture(key)
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames, idx, next_t = [], 0, 0.5
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx / fps >= next_t:
                frames.append(frame)
                next_t += 1.0
            idx += 1
        cap.release()
        _ORIG_1FPS_CACHE[key] = frames
    return _ORIG_1FPS_CACHE[key]


def _nearest_phash_guard(cfg: dict, n_out: int) -> tuple[list[np.ndarray], list[tuple[int, int]]]:
    """复用原片像素的片段必须先自证：每一个输出帧对全片所有 1fps 原帧的最近邻 pHash >= 16。

    sec_indices 按「先输出帧、后原帧」排列，kit 在第一个不达标处立刻进档，最贵的一次成全量复核（约 1s）。
    """
    ref = _orig_1fps_frames(cfg["src_video"])
    sec_indices = [(s, lf) for lf in range(n_out) for s in range(len(ref))]
    return ref, sec_indices


def _rewash_closeup(cfg: dict, src_clip: Path, n_out: int, shot_idx: int, out_mp4: Path) -> dict:
    frames = _read_frames(src_clip)
    if len(frames) > 480:  # 峰值内存上限（<3GB）：长镜头等间隔抽帧，输出仍是均匀 24fps
        keep = np.linspace(0, len(frames) - 1, 480).round().astype(int)
        frames = [frames[i] for i in keep]
    ref, sec_indices = _nearest_phash_guard(cfg, n_out)
    out_frames = rk.universal_closeup_rewash(
        frames, n_out, shot_idx,
        ref_1fps_frames=ref, sec_indices=sec_indices, target_phash=CLOSEUP_TARGET_PHASH,
    )
    rk.write_h264_rawpipe(out_frames, out_mp4, width=WIDTH, height=HEIGHT, fps=FPS, crf=CRF_LOCK)
    uniform = rk.ensure_uniform_24fps(out_mp4, fps=FPS)
    assert uniform["was_uniform"], f"{out_mp4} 24fps 时间戳不均匀: {uniform}"
    return {"out_mp4": str(out_mp4), "n_out_24": len(out_frames), "uniform": uniform["was_uniform"]}


def _render_closeups(cfg: dict, layout: dict) -> dict:
    work = _work(cfg)
    closeups = work / "closeups"
    closeups.mkdir(parents=True, exist_ok=True)
    report = {}
    for row in layout["rows"]:
        idx, kind, need = row["index"], row["kind"], row["frames"]
        if kind != "closeup":
            continue
        src_clip = work / "src_clips" / f"s{idx:02d}.mp4"
        if not src_clip.is_file():
            raise SystemExit(f"缺少源切片 {src_clip}，先跑切片导出")
        names = [f"c{idx:02d}.mp4"]
        for name in names:
            out_mp4 = closeups / name
            if out_mp4.is_file() and _clip_frame_count(out_mp4) >= need:
                uniform = rk.ensure_uniform_24fps(out_mp4, fps=FPS)
                assert uniform["was_uniform"], f"{out_mp4} 24fps 时间戳不均匀: {uniform}"
                report[out_mp4.stem] = {"out_mp4": str(out_mp4), "n_out_24": uniform["nb_frames"], "uniform": True, "reused": True}
                print(f"[prep] {out_mp4.name} 已存在（{uniform['nb_frames']} 帧 >= {need}），跳过")
                continue
            t0 = time.monotonic()
            info = _rewash_closeup(cfg, src_clip, need, idx, out_mp4)
            info["elapsed_sec"] = round(time.monotonic() - t0, 2)
            report[out_mp4.stem] = info
            print(f"[prep] {out_mp4.name} <- universal_closeup_rewash {need} 帧 ({info['elapsed_sec']}s)")
    _dump_json(work / "closeups_report.json", report)
    return report


def _render_stickers(cfg: dict) -> None:
    work = _work(cfg)
    for st in cfg.get("stickers") or []:
        png = work / "stickers_final" / f"{st['key']}.png"
        rk.render_variety_sticker(st.get("style") or "burst_orange", st["text"], png)
        print(f"[prep] sticker {st['key']} [{st.get('style')}] -> {png}")


def _user_credit() -> dict:
    try:
        return json.loads(subprocess.check_output(["dreamina", "user_credit"], text=True))
    except Exception as e:  # noqa: BLE001 - 只读查询失败按未知档位处理，绝不静默扣积分
        return {"error": f"{type(e).__name__}: {e}"}


def _pick_widest_scene_frame(cfg: dict) -> Path:
    """多尺度模板包含度（Projective FoV Containment）选最广全景帧：

    对每个 ai 分镜取中间 60% 内最清晰平稳帧；若其他分镜缩小到 0.48x/0.60x/0.72x 后能高相关嵌入候选帧 i，
    而候选帧 i 缩小后不能嵌入对方，说明候选帧 i 的视场角（FoV）严格更广（全景包含中近景），
    叠加同尺度同伴相似度选出舱门闭合的最广全景主房间帧（纯几何，不受暖色木柜或角标颜色干扰）。
    """
    work = _work(cfg)
    out = work / "refs" / "bg_source_wide.png"
    given = cfg.get("bg_source_frame")
    if given:
        return Path(given)
    cands = []
    for seg in cfg["segments"]:
        if seg["kind"] != "ai":
            continue
        idx = seg["shot_index"]
        clip = work / "src_clips" / f"s{idx:02d}.mp4"
        if not clip.is_file():
            raise SystemExit(f"Shot {idx} 缺源切片，先跑切片导出: {clip}")
        frames = _read_frames(clip)
        if not frames:
            continue
        lo, hi = max(0, int(len(frames) * 0.2)), min(len(frames) - 1, int(len(frames) * 0.8))
        best_f, best_sc = frames[len(frames) // 2], -1e9
        for k in range(max(1, lo), min(len(frames), hi + 1)):
            mot = float(np.mean(cv2.absdiff(frames[k], frames[k - 1])))
            sharp = float(cv2.Laplacian(cv2.cvtColor(frames[k], cv2.COLOR_BGR2GRAY), cv2.CV_64F).var())
            if sharp - 25.0 * mot > best_sc:
                best_sc, best_f = sharp - 25.0 * mot, frames[k]
        g = cv2.resize(cv2.cvtColor(best_f, cv2.COLOR_BGR2GRAY), (180, 320), interpolation=cv2.INTER_AREA)
        cands.append({"idx": idx, "no_actor": bool(seg.get("no_actor")), "g": g, "frame": best_f})
    if not cands:
        raise SystemExit("没有 ai 分镜可用作 bg_anchor 背景源帧")
    n = len(cands)
    for i, ci in enumerate(cands):
        contain_gain = 0.0
        peer_sims = []
        for j, cj in enumerate(cands):
            if i == j:
                continue
            fwd = max(
                float(cv2.matchTemplate(ci["g"], cv2.resize(cj["g"], (int(180 * sc), int(320 * sc))), cv2.TM_CCOEFF_NORMED).max())
                for sc in (0.48, 0.60, 0.72)
            )
            rev = max(
                float(cv2.matchTemplate(cj["g"], cv2.resize(ci["g"], (int(180 * sc), int(320 * sc))), cv2.TM_CCOEFF_NORMED).max())
                for sc in (0.48, 0.60, 0.72)
            )
            contain_gain += fwd - rev
            peer_sims.append(float(cv2.matchTemplate(ci["g"], cv2.resize(cj["g"], (166, 294)), cv2.TM_CCOEFF_NORMED).max()))
        peer_med = float(np.median(sorted(peer_sims)[-max(1, n // 3):])) if peer_sims else 0.0
        ci["fov_score"] = (10.0 if ci["no_actor"] else 0.0) + contain_gain + 1.5 * peer_med
    pick = max(cands, key=lambda c: c["fov_score"])
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), pick["frame"])
    print(f"[prep] bg_anchor 背景源帧 = s{pick['idx']:02d}（FoV 几何包含得分 {pick['fov_score']:+.3f}）-> {out}")
    return out


def _resolve_cabinet_desc(cfg: dict, prev: dict | None = None) -> tuple[str, str | None]:
    """bg_anchor_cabinet_desc 为预设 key / 'random' / 空 -> 展开成同色号同木纹走向的完整改色描述。

    返回 (完整描述, 命中的预设 key)；自定义长描述则 key 为 None。已落盘过的解析结果优先复用，
    保证同一工程重跑 prep 时（尤其 'random'）不会换色重新生图。
    """
    prev = prev or {}
    if prev.get("cabinet_desc"):
        return prev["cabinet_desc"], prev.get("cabinet_key")
    raw = (cfg.get("bg_anchor_cabinet_desc") or "").strip()
    if raw in WARM_CABINET_PALETTES:
        return WARM_CABINET_PALETTES[raw], raw
    if raw in ("", "random"):
        key = random.Random(cfg["video_id"]).choice(sorted(WARM_CABINET_PALETTES))
        print(f"[prep] bg_anchor_cabinet_desc={raw or '空'} -> 固定按 {key} 展开温馨实木色")
        return WARM_CABINET_PALETTES[key], key
    return raw, None


def _ensure_bg_anchor(cfg: dict, approve_credits: bool = False) -> Path:
    """全局唯一背景锚点图 bg_anchor_2k.png：已存在则 0 积分复用，缺失才生图（非 maestro 档位必须显式批准）。"""
    work = _work(cfg)
    target = work / "refs" / "bg_anchor_2k.png"
    given = cfg.get("bg_anchor")
    if given and Path(given).is_file():
        if Path(given).resolve() != target.resolve():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(given, target)
        print(f"[prep] bg_anchor 复用 {given} -> {target}")
        return target
    if target.is_file():
        print(f"[prep] bg_anchor 已就位（0 积分复用）: {target}")
        return target

    job_path = work / "bg_anchor_job.json"
    prev_job = _load_json(job_path, {}) or {}
    prev_status = prev_job.get("status")
    submit_id = prev_job.get("submit_id")
    cabinet_desc, cabinet_key = _resolve_cabinet_desc(cfg, prev_job)

    def _job_meta(**extra) -> dict:
        meta = {"cabinet_desc": cabinet_desc}
        if cabinet_key:
            meta["cabinet_key"] = cabinet_key
        meta.update(extra)
        return meta

    if prev_status in ("submit_unknown", "fail") or (prev_status == "submitting" and not submit_id):
        raise SystemExit(
            f"bg_anchor 处于阻断态 status={prev_status}（见 {job_path}）："
            "请先执行 dreamina list_task 核对任务状态（若已受理将 submit_id 填回 bg_anchor_job.json 并设 status=querying；确认未扣费再删该文件重提），严禁自动重提防重复扣费"
        )

    if submit_id:
        cmd = prev_job.get("cmd") or []
        wide = Path(prev_job.get("wide_src") or (work / "refs" / "bg_source_wide.png"))
        print(f"[prep] 恢复查询已提交的 bg_anchor 任务 submit_id={submit_id}（0 新提交）")
    else:
        wide = _pick_widest_scene_frame(cfg)
        adir = _ascii_dir(cfg)
        adir.mkdir(parents=True, exist_ok=True)
        images = []
        bg_src = adir / "bg_src.png"
        shutil.copyfile(wide, bg_src)
        images.append(bg_src)
        style_ref = cfg.get("bg_style_ref")
        if style_ref:
            style_dst = adir / f"bg_style{Path(style_ref).suffix.lower()}"
            shutil.copyfile(style_ref, style_dst)
            images.append(style_dst)

        credit = _user_credit()
        if (credit.get("vip_level") or "").lower() != "maestro" and not approve_credits:
            raise SystemExit(
                f"缺少 {target}：当前即梦档位 {credit.get('vip_level') or 'unknown'} 生成 1 张 2K 背景锚点图会扣积分，"
                "确认后加 --approve-credits 重跑 prep"
            )

        prompt = BG_ANCHOR_I2I_PROMPT.format(bg_anchor_cabinet_desc=cabinet_desc)
        cmd = ["dreamina", "image2image"] + [f"--images={p}" for p in images] + [
            "--model_version=5.0",
            "--resolution_type=2k",
            "--ratio=9:16",
            "--poll=60",
            f"--prompt={prompt}",
        ]
        _dump_json(job_path, _job_meta(cmd=cmd, wide_src=str(wide), status="submitting"))
        print("[prep] bg_anchor 生图提交: " + " ".join(cmd))
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SUBMIT_TIMEOUT_SEC + 60)
        except subprocess.TimeoutExpired:
            # 超时绝不重提（防重复扣费）：先落 submit_unknown，再用 list_task 让用户核对
            data = _load_json(job_path, {})
            data.update(_job_meta())
            data["status"] = "submit_unknown"
            data["last_submit_err"] = "TimeoutExpired; 先核对 dreamina list_task 再决定是否重提（防重复扣费）"
            _dump_json(job_path, data)
            try:
                listing = subprocess.run(["dreamina", "list_task"], capture_output=True, text=True, timeout=30)
                data["list_task"] = ((listing.stdout or "") + (listing.stderr or ""))[:2000]
            except Exception as le:  # noqa: BLE001 - 保持已落盘的 submit_unknown 阻断态
                data["list_task"] = f"{type(le).__name__}: {le}"
            _dump_json(job_path, data)
            raise SystemExit(
                f"bg_anchor 生图提交超时：已落 submit_unknown 到 {job_path}，先核对 dreamina list_task 再决定是否重提（防重复扣费）"
            )
        text = (proc.stdout or "").strip()
        if proc.returncode != 0 or not text.startswith("{"):
            _dump_json(job_path, _job_meta(cmd=cmd, wide_src=str(wide), status="fail", err=((proc.stdout or "") + (proc.stderr or ""))[:500]))
            raise SystemExit(f"bg_anchor 生图提交失败 rc={proc.returncode}: {((proc.stdout or '') + (proc.stderr or ''))[:500]}")
        data = json.loads(text)
        submit_id = data.get("submit_id")
        if not submit_id:
            _dump_json(job_path, _job_meta(cmd=cmd, wide_src=str(wide), status="submit_unknown", raw=text[:500]))
            raise SystemExit(f"bg_anchor 生图未返回 submit_id: {text[:500]}")
        _dump_json(job_path, _job_meta(cmd=cmd, wide_src=str(wide), submit_id=submit_id,
                                      status=data.get("gen_status") or "querying"))

    raw_dir = work / "refs" / "bg_anchor_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + BG_ANCHOR_POLL_SEC
    while True:
        query = subprocess.run(
            ["dreamina", "query_result", f"--submit_id={submit_id}", f"--download_dir={raw_dir}"],
            capture_output=True, text=True, timeout=QUERY_TIMEOUT_SEC,
        )
        qout = (query.stdout or "").strip()
        qdata = json.loads(qout) if qout.startswith("{") else {}
        status = qdata.get("gen_status")
        imgs = sorted(p for p in raw_dir.iterdir() if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"})
        if status == "success" and imgs:
            shutil.copyfile(imgs[0], target)
            _dump_json(job_path, _job_meta(cmd=cmd, wide_src=str(wide), submit_id=submit_id,
                                          status="success", png=str(imgs[0])))
            print(f"[prep] bg_anchor -> {target}")
            return target
        if status == "fail":
            _dump_json(job_path, _job_meta(cmd=cmd, wide_src=str(wide), submit_id=submit_id,
                                          status="fail", fail_reason=qout[:500]))
            raise SystemExit(f"bg_anchor 生图失败（submit_id={submit_id}）: {qout[:500]}")
        if time.monotonic() > deadline:
            raise SystemExit(
                f"bg_anchor 生图未在 {BG_ANCHOR_POLL_SEC:.0f}s 内完成（submit_id={submit_id}）："
                f"产物稍后用 `dreamina query_result --submit_id={submit_id} --download_dir={raw_dir}` 续取，严禁重提"
            )
        time.sleep(POLL_INTERVAL_SEC)


def cmd_prep(cfg: dict, approve_credits: bool = False) -> int:
    work = _work(cfg)
    for sub in ("src_clips", "closeups", "voice_clone", "gen_raw", "gen_retimed", "stickers_final", "dense_montage"):
        (work / sub).mkdir(parents=True, exist_ok=True)
    segments = cfg["segments"]
    _validate_subtitles(segments)

    shots = _load_shots(cfg)
    by_idx = {s["shot_index"]: s for s in shots}
    src = cfg["src_video"]

    # 1) 零切点硬门禁导出：所有分镜都出源切片
    exported = {}
    for seg in segments:
        idx = seg["shot_index"]
        sh = by_idx.get(idx)
        if sh is None:
            raise SystemExit(f"Shot {idx} 不在 shots.json 中")
        rec = rk.export_verified_atomic_clip(
            src, sh["safe_start_frame"], sh["safe_end_frame"],
            work / "src_clips" / f"s{idx:02d}.mp4",
            work / "src_clips" / f"s{idx:02d}_first.jpg",
        )
        exported[str(idx)] = rec
        print(f"[prep] s{idx:02d}.mp4 导出 {rec['exported_frames']} 帧 / 可用 {rec['valid_frames_24fps']} 帧 @24fps")
    _dump_json(work / "exported_clips.json", exported)

    # 2) 全片唯一背景锚点图（已就位则 0 积分复用），再统一落 /tmp 纯 ASCII 上传目录
    cfg["bg_anchor"] = str(_ensure_bg_anchor(cfg, approve_credits))
    staged = _stage_ascii_inputs(cfg)
    print(f"[prep] 即梦上传目录 {_ascii_dir(cfg)}: {sorted(staged)}")

    # 3) 配音全洗（缺哪句补哪句，绝不重跑已就位的句子）
    _synth_missing_voices(cfg)

    # 4) 全片帧布局 + 单句不超镜硬门禁（在花任何 Dreamina 积分前硬停）
    layout = _compute_layout(cfg)
    print(f"[prep] 帧布局 {layout['duration_frames']} 帧 / {layout['duration_sec']}s，全部配音均未超镜")

    # 5) 真机特写去重 + split 分屏上半底片
    _render_closeups(cfg, layout)

    # 6) 无黑框综艺花字
    _render_stickers(cfg)

    plan_path = _write_plan(cfg, layout)
    print(f"[prep] 完成 -> {plan_path}")
    return 0


# ============================================================================
# generate：积分预审 + 提交/轮询/落盘（未 --approve-credits 一律 0 提交）
# ============================================================================
def _jobs_path(cfg: dict) -> Path:
    return _work(cfg) / "dreamina_jobs.json"


def _load_jobs(cfg: dict) -> dict:
    return _load_json(_jobs_path(cfg), {})


def _save_jobs(cfg: dict, jobs: dict) -> None:
    _dump_json(_jobs_path(cfg), jobs)


def _exported_duration(cfg: dict, idx: int) -> float:
    rec = (_load_json(_work(cfg) / "exported_clips.json", {}) or {}).get(str(idx))
    if rec:
        return float(rec["exported_duration_sec"])
    clip = _work(cfg) / "src_clips" / f"s{idx:02d}.mp4"
    if clip.is_file():
        return _probe_duration(clip)
    raise SystemExit(f"Shot {idx} 无导出片段，先跑 prep")


def _dreamina_cmd(cfg: dict, seg: dict, duration: int) -> list[str]:
    """KISS 零裁剪：全片只传同一张 bg_anchor.jpg；只有正脸交互镜额外传统一音色卡 timbre_ref.wav。"""
    idx = seg["shot_index"]
    adir = _ascii_dir(cfg)
    clip = adir / f"s{idx:02d}.mp4"
    assets = _ascii_assets(cfg)
    keys = ("bg_anchor",) if seg.get("no_actor") else ("bg_anchor", "head_3view", "body_3view")
    cmd = ["dreamina", "multimodal2video", f"--video={clip}"]
    for key in keys:
        if key not in assets:
            raise SystemExit(f"缺少参考图 {key}: 先跑 prep 生成 {_work(cfg) / 'refs' / 'bg_anchor_2k.png'}")
        cmd.append(f"--image={assets[key]}")
    if _is_speak_ai_seg(seg):
        ref_wav = cfg.get("ref_wav")
        if not ref_wav or not Path(ref_wav).is_file():
            raise SystemExit(f"存在开口人物镜但未配置有效 ref_wav: {ref_wav!r}")
        timbre = adir / "timbre_ref.wav"
        if not timbre.is_file():
            raise SystemExit(f"缺统一音色卡 {timbre}（prep 未落盘？先重跑 prep）")
        cmd.append(f"--audio={timbre}")
    cmd += [
        f"--model_version={MODEL_LOCK}",
        f"--video_resolution={RES_LOCK}",
        f"--ratio={RATIO_LOCK}",
        f"--duration={duration}",
        "--poll=0",
        f"--prompt={build_prompt(cfg, seg)}",
    ]
    return cmd


def _face_audit_sheet(work: Path, done: list[tuple[int, Path]]) -> Path:
    """3 帧紧贴面部抽检图：每镜取 15%/50%/85%，裁上半区正脸，横向拼接便于肉眼核对闭嘴。"""
    rows = []
    for idx, clip in done:
        frames = _read_frames(clip)
        if not frames:
            continue
        picks = [frames[min(len(frames) - 1, int(len(frames) * f))] for f in (0.15, 0.5, 0.85)]
        tiles = []
        for fr in picks:
            crop = fr[40:840, 240:840]
            tile = cv2.resize(crop, (300, 400), interpolation=cv2.INTER_AREA)
            tiles.append(tile)
        row = np.hstack(tiles)
        cv2.rectangle(row, (0, 0), (120, 36), (0, 0, 0), -1)
        cv2.putText(row, f"s{idx:02d}", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        rows.append(row)
    sheet = np.vstack(rows) if rows else np.zeros((400, 900, 3), dtype=np.uint8)
    out = work / "audit_faces.jpg"
    cv2.imwrite(str(out), sheet, [cv2.IMWRITE_JPEG_QUALITY, 92])
    return out


def _has_audio_stream(mp4_path: str | Path) -> bool:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=index", "-of", "csv=p=0", str(mp4_path)],
        text=True,
    ).strip()
    return bool(out)


def _detect_speech_end_sec(mp4_path: str | Path, win_sec: float = 0.02, rms_threshold: float = 0.015) -> float | None:
    """扫即梦原生音轨找最后一个人声窗的结束秒（20ms 窗，RMS > 0.015，末尾残窗同样计入）。

    即梦会把整句张嘴->换气->合唇的微笑尾巴一起生成，尾巴比自己合成的干声长；pack 阶段按这个
    秒数把整段等比压回 nf 帧，让口型起止刚好压在 VoxCPM 干声区间内（不依赖即梦音轨本身）。
    """
    if not _has_audio_stream(mp4_path):
        return None
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(mp4_path), "-map", "0:a:0",
         "-ac", "1", "-ar", "16000", "-f", "s16le", "-"],
        capture_output=True,
    )
    if raw.returncode != 0 or not raw.stdout:
        return None
    sr = 16000
    pcm = np.frombuffer(raw.stdout[: len(raw.stdout) // 2 * 2], dtype=np.int16).astype(np.float32) / 32768.0
    win = max(1, int(round(win_sec * sr)))
    n_win = len(pcm) // win
    tail = pcm[n_win * win:]
    rms = np.sqrt(np.mean(pcm[: n_win * win].reshape(n_win, win) ** 2, axis=1))
    voiced = np.nonzero(rms > rms_threshold)[0]
    # 末尾不足 20ms 整窗的尾部样本同样要算 RMS：否则残窗里的尾巴会被漏判、收口时咬掉尾音
    tail_voiced = tail.size >= 1 and float(np.sqrt(np.mean(tail ** 2))) > rms_threshold
    if voiced.size == 0 and not tail_voiced:
        return None
    end_sec = float((int(voiced[-1]) + 1) * win_sec) if voiced.size else 0.0
    if tail_voiced:
        end_sec = max(end_sec, len(pcm) / sr)
    return round(min(end_sec, len(pcm) / sr), 4)


def _finalize_generated(cfg: dict, idx: int, job: dict, jobs: dict) -> None:
    work = _work(cfg)
    src_mp4 = Path(job["video_path"])
    out_mp4 = work / "gen_retimed" / f"s{idx:02d}_24fps.mp4"
    seg = next((s for s in cfg["segments"] if s["shot_index"] == idx), {})
    if _is_speak_ai_seg(seg):
        job["native_speech_end_sec"] = _detect_speech_end_sec(src_mp4)
    else:
        # 等比收口只服务开口镜：闭嘴/无人镜清掉历史值，防旧 job 残留把动作镜压变形
        job.pop("native_speech_end_sec", None)
    info = rk.ensure_uniform_24fps(src_mp4, out_mp4, fps=FPS)
    job["retimed_path"] = str(out_mp4)
    job["retime"] = info
    _save_jobs(cfg, jobs)
    done = [(int(k), Path(v["retimed_path"])) for k, v in jobs.items() if v.get("retimed_path")]
    sheet = _face_audit_sheet(work, sorted(done))
    print(f"[generate] Shot {idx:02d} 24fps 均匀化 -> {out_mp4} ({info['r_frame_rate']}, {info['nb_frames']} 帧)，面部抽检 {sheet}")
    if "native_speech_end_sec" in job:
        print(f"[generate] Shot {idx:02d} 即梦原生人声结束 native_speech_end_sec={job['native_speech_end_sec']}（pack 等比收口用）")


def _poll_active(cfg: dict, jobs: dict) -> None:
    for key, job in jobs.items():
        if job.get("status") != "querying" or not job.get("submit_id"):
            continue
        idx = int(key)
        dl = _work(cfg) / "gen_raw" / f"s{idx:02d}"
        dl.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(
            ["dreamina", "query_result", f"--submit_id={job['submit_id']}", f"--download_dir={dl}"],
            capture_output=True, text=True, timeout=QUERY_TIMEOUT_SEC,
        )
        if proc.returncode != 0 or not proc.stdout.strip().startswith("{"):
            continue
        data = json.loads(proc.stdout)
        job["last_est_sec"] = data.get("estimated_remaining_seconds")
        status = data.get("gen_status", "querying")
        if status == "success":
            mp4s = sorted(dl.glob("*.mp4"))
            if mp4s:
                job["status"] = "success"
                job["video_path"] = str(mp4s[0])
                job["completed_at_sec"] = round(time.monotonic() - job.get("t_start", time.monotonic()), 2)
                print(f"[generate] Shot {idx:02d} 完成: {mp4s[0]}")
                _save_jobs(cfg, jobs)
                _finalize_generated(cfg, idx, job, jobs)
        elif status == "fail":
            job["status"] = "fail"
            job["fail_reason"] = data.get("fail_reason", proc.stdout[:500])
            print(f"[generate] Shot {idx:02d} 失败: {job['fail_reason']}")
            _save_jobs(cfg, jobs)


def _try_submit_pending(cfg: dict, jobs: dict) -> None:
    """每轮只把 pending 分镜串行提交一次；撞并发上限/提交异常就原地返回，绝不自作主张重提。"""
    seg_by_idx = {s["shot_index"]: s for s in cfg["segments"]}
    for key, job in jobs.items():
        if job.get("status") != "pending":
            continue
        idx = int(key)
        seg = seg_by_idx.get(idx, {})
        cmd = _dreamina_cmd(cfg, seg, job["duration"])
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=SUBMIT_TIMEOUT_SEC)
        except subprocess.TimeoutExpired:
            job["status"] = "submit_unknown"
            job["last_submit_err"] = "TimeoutExpired; 先核对 dreamina list_task 再决定是否重提（防重复扣费）"
            _save_jobs(cfg, jobs)
            try:
                listing = subprocess.run(["dreamina", "list_task"], capture_output=True, text=True, timeout=30)
                job["last_submit_err"] += ": " + (listing.stdout or "")[:400]
                _save_jobs(cfg, jobs)
            except Exception as le:  # noqa: BLE001 - 保持已落盘的 submit_unknown 阻断态
                job["last_submit_err"] += f" (list_task 亦异常: {type(le).__name__}: {le})"
                _save_jobs(cfg, jobs)
            print(f"[generate] Shot {idx:02d} 提交超时：已先持久化 submit_unknown 并 halt，绝不盲目重提（防重复扣费）")
            return
        combined = (proc.stdout or "") + " " + (proc.stderr or "")
        if proc.returncode == 0 and proc.stdout.strip().startswith("{"):
            data = json.loads(proc.stdout)
            job["submit_id"] = data["submit_id"]
            job["credit_count"] = data.get("credit_count")
            job["est_sec"] = data.get("estimated_remaining_seconds")
            job["status"] = "querying"
            job["t_start"] = time.monotonic()
            _save_jobs(cfg, jobs)
            print(f"[generate] Shot {idx:02d} 已提交 submit_id={job['submit_id']} credits={job['credit_count']}")
            time.sleep(1.5)
        elif "ExceedConcurrencyLimit" in combined or "1310" in combined:
            print(f"[generate] Shot {idx:02d} 撞 {MODEL_LOCK} 并发上限，原地等待，严禁跨模型乱投")
            return
        else:
            job["last_submit_err"] = combined[:500]
            job["status"] = "submit_error"
            _save_jobs(cfg, jobs)
            print(f"[generate] Shot {idx:02d} 提交报错 rc={proc.returncode}: {combined[:300]}")
            return


def cmd_generate(cfg: dict, approve_credits: bool) -> int:
    work = _work(cfg)
    _validate_subtitles(cfg["segments"])
    # 在消耗任何 Dreamina 积分前强制验证全部配音已就位且无单句超镜
    _compute_layout(cfg)
    for sub in ("gen_raw", "gen_retimed"):
        (work / sub).mkdir(parents=True, exist_ok=True)
    # /tmp 可能已被清空：generate 自己重新落 bg_anchor + 三视图 + 源切片，绝不要求重跑 prep
    staged = _stage_ascii_inputs(cfg)
    print(f"[generate] 即梦上传目录 {_ascii_dir(cfg)}: {sorted(staged)}")
    jobs = _load_jobs(cfg)

    pending = []
    print(f"{'shot':>4} {'kind':>7} {'dur':>4} {'credits':>11}  status")
    gen_segments = [s for s in cfg["segments"] if s["kind"] in ("ai", "split")]
    for seg in gen_segments:
        idx = seg["shot_index"]
        job = jobs.get(str(idx), {})
        job.setdefault("shot", idx)
        if job.get("status") == "success":
            jobs[str(idx)] = job
            print(f"{idx:>4} {seg['kind']:>7} {'':>4} {'':>11}  success ({job.get('submit_id')})")
            continue
        duration = max(4, int(math.ceil(_exported_duration(cfg, idx))))
        job["duration"] = duration
        job.setdefault("status", "pending")
        jobs[str(idx)] = job
        pending.append((seg, duration))
        print(f"{idx:>4} {seg['kind']:>7} {duration:>4} {'9~12/s':>11}  {job['status']}")
    _save_jobs(cfg, jobs)

    credit = _user_credit()
    print(f"[generate] 当前即梦余额: {json.dumps(credit, ensure_ascii=False)}")

    total_sec = sum(d for _, d in pending)
    lo, hi = CREDITS_PER_SEC_RANGE
    print(f"[generate] 待生成 {len(pending)} 镜 / 合计 {total_sec}s，预估 {total_sec * lo}~{total_sec * hi} 积分")
    for seg, duration in pending:
        print("[generate] 预览: " + " ".join(_dreamina_cmd(cfg, seg, duration)))
    actor_desc = cfg.get("actor_desc") or DEFAULT_ACTOR_DESC
    print("[generate] 固定 KISS Prompt（全片统一背景锚点约束）:")
    print("[generate]   正脸交互镜: " + KISS_SPEAK_PROMPT.format(spoken_line="<本镜口播稿>", actor_desc=actor_desc))
    print("[generate]   闭嘴家务镜: " + KISS_SILENT_PROMPT.format(actor_desc=actor_desc))
    print("[generate]   无人空镜: " + KISS_NO_ACTOR_PROMPT)

    if not pending:
        print("[generate] 全部分镜已 success：本次 0 积分、0 提交")
        return 0
    if not approve_credits:
        print("[generate] 未传 --approve-credits：只做积分预审，未提交任何任务（0 积分已花）")
        return 0

    gen_idx = {s["shot_index"] for s in gen_segments}
    while True:
        _poll_active(cfg, jobs)
        _try_submit_pending(cfg, jobs)
        states = {k: v.get("status") for k, v in jobs.items() if int(k) in gen_idx}
        stuck = {k: s for k, s in states.items() if s in ("submit_unknown", "submit_error", "fail")}
        if stuck:
            print(f"[generate] 分镜 {stuck} 未正常提交/失败：已停止自动重试（每笔重跑都需用户单独批积分，先核对 `dreamina list_task` 防重复扣费）")
            return 1
        if all(s == "success" for s in states.values()):
            break
        active = [(k, v.get("last_est_sec")) for k, v in jobs.items() if v.get("status") == "querying"]
        print(f"[generate] 进行中 active={active}")
        time.sleep(POLL_INTERVAL_SEC)

    try:
        print(f"[generate] 结束余额: {subprocess.check_output(['dreamina', 'user_credit'], text=True).strip()}")
    except Exception:  # noqa: BLE001
        pass
    failed = [k for k, v in jobs.items() if v.get("status") != "success"]
    if failed:
        print(f"[generate] 仍有未成功分镜: {failed}（不自动重跑，需用户单独批准积分）")
        return 1
    return 0

# ============================================================================
# pack：1080p 成片 + 5 轨剪映草稿 + 端到端验收
# ============================================================================
def _srt_ts(sec: float) -> str:
    ms = int(round(sec * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _ass_ts(sec: float) -> str:
    cs = int(round(sec * 100))
    return f"{cs // 360000:d}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _build_voiceover(work: Path, rows: list[dict], total_dur: float) -> Path:
    dense = work / "dense_montage"
    vo_cmd = ["ffmpeg", "-v", "error", "-y"]
    for r in rows:
        vo_cmd += ["-i", r["voice"]]
    chains = []
    for i, r in enumerate(rows):
        delay_ms = round((r["output_start_frame"] + 1) / FPS * 1000)
        chains.append(f"[{i}:a]adelay={delay_ms}|{delay_ms}[a{i}]")
    chains.append(
        "".join(f"[a{i}]" for i in range(len(rows)))
        + f"amix=inputs={len(rows)}:duration=longest:normalize=0,apad,atrim=0:{total_dur:.6f}[out]"
    )
    out = dense / "voiceover.wav"
    subprocess.run(vo_cmd + ["-filter_complex", ";".join(chains), "-map", "[out]", "-ar", "44100", "-ac", "1", str(out)], check=True)
    return out


def _assert_zero_overlap(vo_wav: Path, rows: list[dict]) -> None:
    """逐窗证明：相邻分镜音频 0 重叠（间隔区必须真静音，窗口内必须有声）。"""
    with wave.open(str(vo_wav), "rb") as wf:
        sr = wf.getframerate()
        buf = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    wins = []
    for r in rows:
        st = (r["output_start_frame"] + 1) / FPS
        wins.append((st, st + r["voice_duration"]))
    for k in range(1, len(wins)):
        assert wins[k][0] > wins[k - 1][1], f"配音窗口重叠: {wins[k - 1]} vs {wins[k]}"
    for a, b in zip(wins, wins[1:]):
        g0, g1 = int((a[1] + 0.002) * sr), int((b[0] - 0.001) * sr)
        if g1 > g0:
            peak = float(np.max(np.abs(buf[g0:g1])))
            assert peak < 1e-3, f"配音间隔区有串音（peak={peak:.4f}），说明相邻句子重叠"
    for st, ed in wins:
        seg = buf[int(st * sr):int(min(ed, len(buf) / sr) * sr)]
        assert seg.size and float(np.max(np.abs(seg))) > 0.05, "配音窗口内静音，说明音频未落位"


def _write_subtitles(dense: Path, rows: list[dict]) -> tuple[Path, Path]:
    if not FONT_PATH.is_file():
        raise SystemExit(f"缺少强制要求的美的商用授权字幕字体: {FONT_PATH}")
    fc_out = subprocess.check_output(["fc-scan", "--format=%{family}", str(FONT_PATH)], text=True).strip()
    font_family = fc_out.split(",")[0].strip()
    if not font_family:
        raise SystemExit(f"无法从 {FONT_PATH} 解析字体族名")
    print(f"[pack] 美的授权字幕字体: {FONT_PATH.name} -> {font_family}")

    srt_entries, ass_events = [], []
    prev_end_us = 0
    for r in rows:
        text, parts = r["text"], r["subparts"]
        seg_start = (r["output_start_frame"] + 1) / FPS
        seg_end_limit = (r["output_start_frame"] + r["frames"]) / FPS
        pos = seg_start
        for j, part in enumerate(parts):
            end = seg_start + r["voice_duration"] if j == len(parts) - 1 else pos + r["voice_duration"] * len(part) / len(text)
            end = min(end, seg_end_limit - 0.005)
            st_us, ed_us = int(round(pos * 1_000_000)), int(round(end * 1_000_000))
            if st_us < prev_end_us:
                st_us = prev_end_us
                pos = st_us / 1_000_000
            assert ed_us > st_us, f"零长/负长字幕区间: {part!r}"
            prev_end_us = ed_us
            srt_entries.append(f"{len(srt_entries) + 1}\n{_srt_ts(pos)} --> {_srt_ts(end)}\n{part}\n")
            ass_events.append(f"Dialogue: 0,{_ass_ts(pos)},{_ass_ts(end)},Default,,0,0,0,,{{\\pos({WIDTH // 2},{SUB_Y})}}{part}")
            pos = end

    srt_path, ass_path = dense / "subtitles.srt", dense / "subtitles.ass"
    srt_path.write_text("\n".join(srt_entries), encoding="utf-8")
    ass_header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {WIDTH}
PlayResY: {HEIGHT}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_family},{SUB_FONT_SIZE},&H00FFFFFF,&H00FFFFFF,&H00101010,&H00000000,0,0,0,0,100,100,0,0,1,7,0,5,60,60,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ass_path.write_text(ass_header + "\n".join(ass_events) + "\n", encoding="utf-8")
    return srt_path, ass_path


def _clip_source(cfg: dict, row: dict) -> tuple[list[np.ndarray], dict]:
    """按分镜类型取重建帧：ai=成片镜头，closeup=真机特写，split=上半特写+下半 AI 合成。

    仅开口镜（`_is_speak_ai_seg(row)`）且 offset=0 时，若本镜带了即梦原生人声结束秒，就把整段
    张嘴->换气->合唇的微笑尾巴等比压回本镜配音 nf 帧，让口型起止刚好压在 VoxCPM 干声区间内
    （旧工程无该字段则原样截取）。
    """
    work = _work(cfg)
    idx, nf, kind = row["index"], row["frames"], row["kind"]
    if kind == "closeup":
        return _read_frames(work / "closeups" / f"c{idx:02d}.mp4", nf), {}
    offset = int(row.get("ai_frame_offset") or 0)
    ret_path = work / "gen_retimed" / f"s{idx:02d}_24fps.mp4"
    total_ret = _clip_frame_count(ret_path)
    if offset < 0 or offset + nf > total_ret:
        raise SystemExit(f"Shot {idx} ai_frame_offset({offset}) + frames({nf}) 超出 {ret_path.name} 总帧数 {total_ret}")
    # 严守 1.0x 真人原速：禁止 np.linspace 抽帧快进（抽帧会导致嘴部与手势跳帧鬼畜）
    span_frames = None
    raw_ai = _read_frames(ret_path, offset + nf)
    ai_frames = raw_ai[offset : offset + nf]
    if kind == "ai":
        meta = {"ai_frame_offset": offset} if offset else {}
        if span_frames is not None:
            meta["native_speech_end_sec"] = round(float(speech_end), 4)
            meta["speech_end_span_frames"] = span_frames
        obox = row.get("overlay_orig_box")
        if obox:
            x0, y0, x1, y1 = (int(v) for v in obox)
            f0_im = cv2.imread(str(work / "src_clips" / f"s{idx:02d}_first.jpg"))
            if f0_im is not None:
                f0_im = cv2.resize(f0_im, (WIDTH, HEIGHT), interpolation=cv2.INTER_LANCZOS4)
                patch = f0_im[y0:y1, x0:x1].copy()
                for fr in ai_frames:
                    fr[y0:y1, x0:x1] = patch
                meta["overlay_orig_box"] = [x0, y0, x1, y1]
        return ai_frames, meta
    split_y = int(row["split_y"])
    src_raw = _read_frames(work / "src_clips" / f"s{idx:02d}.mp4")
    idxs_24 = [min(len(src_raw) - 1, int(round(k * len(src_raw) / max(1, nf)))) for k in range(nf)]
    top = [src_raw[i] for i in idxs_24]
    recolor_sleeve = bool(row.get("recolor_navy_sleeve"))
    frames = []
    for tf, bf in zip(top, ai_frames):
        comp = tf.copy()
        sub = bf[split_y:].copy()
        if recolor_sleeve and sub.shape[0] > 270:
            roi = sub[270:, :].copy()
            hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV).astype(np.float32)
            navy = (hsv[:, :, 0] >= 98) & (hsv[:, :, 0] <= 135) & (hsv[:, :, 1] >= 42) & (hsv[:, :, 2] <= 155)
            alpha = (cv2.GaussianBlur(navy.astype(np.uint8) * 255, (9, 9), 2.0).astype(np.float32) / 255.0)[..., None]
            lum = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32)[..., None]
            cream = np.clip(np.array([196.0, 212.0, 224.0])[None, None, :] * (0.72 + 0.45 * (lum / 120.0)), 0, 255)
            sub[270:, :] = np.clip(cream * alpha + roi.astype(np.float32) * (1.0 - alpha), 0, 255).astype(np.uint8)
        comp[split_y:] = sub
        frames.append(comp)
    ref, sec_indices = _nearest_phash_guard(cfg, nf)
    frames = rk.universal_closeup_rewash(
        frames, nf, idx, ref_1fps_frames=ref, sec_indices=sec_indices, target_phash=CLOSEUP_TARGET_PHASH,
    )
    return frames, {"split_y": split_y, "recolor_navy_sleeve": recolor_sleeve}


def _concat_clips(dense: Path, rows: list[dict]) -> Path:
    (dense / "concat.txt").write_text("".join(f"file 'video_{r['index']:02d}.mp4'\n" for r in rows), encoding="utf-8")
    picture = dense / "picture.mp4"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(dense / "concat.txt"),
         "-c", "copy", "-movflags", "+faststart", str(picture)],
        check=True,
    )
    uniform = rk.ensure_uniform_24fps(picture, fps=FPS)
    assert uniform["was_uniform"], f"picture.mp4 时间戳不均匀: {uniform}"
    return picture


def _alpha_bbox_center(png_path: Path) -> tuple[float, float, int, int]:
    im = Image.open(png_path).convert("RGBA")
    bbox = im.getchannel("A").getbbox()
    w, h = im.size
    if not bbox:
        return w / 2.0, h / 2.0, w, h
    return (bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0, w, h


def _burn_final(cfg: dict, picture: Path, mix_m4a: Path, total_dur: float, stickers: list[dict]) -> Path:
    work = _work(cfg)
    dense = work / "dense_montage"
    final_mp4 = work / (cfg.get("final_name") or f"{cfg['video_id']}_成片_1080p.mp4")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(picture)]
    for st in stickers:
        cmd += ["-i", st["png"]]
    cmd += ["-i", str(mix_m4a)]

    vf_parts = []
    cur = "[0:v]"
    for i, st in enumerate(stickers, start=1):
        acx, acy, _, _ = _alpha_bbox_center(Path(st["png"]))
        nxt = f"[v{i}]"
        vf_parts.append(
            f"{cur}[{i}:v]overlay=x={round(st['cx'] - acx, 1)}:y={round(st['cy'] - acy, 1)}"
            f":enable='between(t,{st['start_sec']},{st['end_sec']})'{nxt}"
        )
        cur = nxt
    ass_escaped = str(dense / "subtitles.ass").replace(":", "\\:").replace("'", "\\'")
    fonts_escaped = str(FONT_PATH.parent).replace(":", "\\:").replace("'", "\\'")
    vf_parts.append(f"{cur}ass=filename='{ass_escaped}':fontsdir='{fonts_escaped}'[vout]")

    audio_idx = len(stickers) + 1
    subprocess.run(
        cmd + [
            "-filter_complex", ";".join(vf_parts),
            "-map", "[vout]", "-map", f"{audio_idx}:a:0",
            "-c:v", "libx264", "-preset", "fast", "-crf", str(CRF_LOCK), "-pix_fmt", "yuv420p",
            "-r", str(FPS), "-c:a", "copy", "-map_metadata", "-1", "-movflags", "+faststart",
            "-t", f"{total_dur:.6f}", str(final_mp4),
        ],
        check=True,
    )
    uniform = rk.ensure_uniform_24fps(final_mp4, fps=FPS)
    assert uniform["was_uniform"], f"成片 24fps 时间戳不均匀: {uniform}"
    return final_mp4


def _f_us(frame: int) -> int:
    return int(round(frame * 1_000_000 / FPS))


def _build_draft(cfg: dict, rows: list[dict], stickers: list[dict], total_frames: int, mix_info: dict) -> tuple[Path, Path]:
    work = _work(cfg)
    dense = work / "dense_montage"
    draft_root = dense / "剪映草稿"
    draft_name = cfg.get("draft_name") or f"{cfg['video_id']}_洗稿_字幕贴纸_1080x1920_24fps"
    if (draft_root / draft_name).exists():
        shutil.rmtree(draft_root / draft_name)
    draft_root.mkdir(parents=True, exist_ok=True)

    script = DraftFolder(str(draft_root)).create_draft(draft_name, WIDTH, HEIGHT, FPS, allow_replace=True)
    mat_dir = draft_root / draft_name / "materials"
    mat_dir.mkdir(parents=True, exist_ok=True)

    track_video = script.append_track(TrackSpec(TrackType.video, name="主视频轨"))
    track_sticker = script.append_track(TrackSpec(TrackType.video, name="贴纸轨"))
    track_text = script.append_track(TrackSpec(TrackType.text, name="口播字幕轨"))
    track_voice = script.append_track(TrackSpec(TrackType.audio, name="口播画外音轨"))
    track_bgm = script.append_track(TrackSpec(TrackType.audio, name="BGM轨"))

    for r in rows:
        idx = r["index"]
        v_dst = mat_dir / f"video_{idx:02d}.mp4"
        shutil.copyfile(dense / f"video_{idx:02d}.mp4", v_dst)
        mat = VideoMaterial(str(v_dst))
        st_u = _f_us(r["output_start_frame"])
        dur_u = _f_us(r["output_start_frame"] + r["frames"]) - st_u
        script.add_segment(
            VideoSegment(mat, trange(st_u, dur_u), source_timerange=trange(0, dur_u), volume=0.0),
            track=track_video,
        )

    for st in stickers:
        p_src = Path(st["png"])
        p_dst = mat_dir / p_src.name
        shutil.copyfile(p_src, p_dst)
        acx, acy, pw, ph = _alpha_bbox_center(p_dst)
        tx = ((st["cx"] - (acx - pw / 2.0)) - WIDTH / 2.0) / (WIDTH / 2.0)
        ty = ((HEIGHT / 2.0) - (st["cy"] - (acy - ph / 2.0))) / (HEIGHT / 2.0)
        mat = VideoMaterial(str(p_dst))
        st_u = int(round(st["start_sec"] * 1_000_000))
        dur_u = int(round(st["end_sec"] * 1_000_000)) - st_u
        script.add_segment(
            VideoSegment(mat, trange(st_u, dur_u), clip_settings=ClipSettings(transform_x=tx, transform_y=ty)),
            track=track_sticker,
        )

    srt_text = (dense / "subtitles.srt").read_text(encoding="utf-8")
    ty_sub = (HEIGHT / 2.0 - SUB_Y) / (HEIGHT / 2.0)
    for block in [b for b in re.split(r"\n\s*\n", srt_text.strip()) if b.strip()]:
        lines = [x.strip() for x in block.splitlines() if x.strip()]
        m = re.match(r"(\d+):(\d+):(\d+),(\d+)\s*-->\s*(\d+):(\d+):(\d+),(\d+)", lines[1])
        h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(v) for v in m.groups())
        st_u = ((h1 * 3600 + m1 * 60 + s1) * 1000 + ms1) * 1000
        ed_u = ((h2 * 3600 + m2 * 60 + s2) * 1000 + ms2) * 1000
        script.add_segment(
            TextSegment(
                "".join(lines[2:]),
                trange(st_u, ed_u - st_u),
                style=TextStyle(size=9.5, color=(1.0, 1.0, 1.0), align=1),
                clip_settings=ClipSettings(transform_y=ty_sub),
                border=TextBorder(color=(0.08, 0.08, 0.08), width=40.0),
            ),
            track=track_text,
        )

    vo_dst = mat_dir / "voiceover.wav"
    shutil.copyfile(dense / "voiceover.wav", vo_dst)
    am_vo = AudioMaterial(str(vo_dst))
    total_us = _f_us(total_frames)
    vo_dur_us = min(total_us, am_vo.duration)
    script.add_segment(
        AudioSegment(am_vo, trange(0, vo_dur_us), source_timerange=trange(0, vo_dur_us), volume=1.0),
        track=track_voice,
    )

    bgm_src = Path(cfg["bgm"])
    bgm_dst = mat_dir / f"bgm{bgm_src.suffix.lower()}"
    shutil.copyfile(bgm_src, bgm_dst)
    am_bgm = AudioMaterial(str(bgm_dst))
    bgm_trim_us = int(round(mix_info.get("bgm_trimmed_sec", 0.0) * 1_000_000))
    bgm_dur_us = min(total_us, max(0, am_bgm.duration - bgm_trim_us))
    script.add_segment(
        AudioSegment(am_bgm, trange(0, bgm_dur_us), source_timerange=trange(bgm_trim_us, bgm_dur_us), volume=0.08),
        track=track_bgm,
    )
    script.save()

    draft_dir = draft_root / draft_name
    # 将美的商用授权正大黑字体文件随草稿打包，并在草稿文本素材中显式绑定该字体路径
    if not FONT_PATH.is_file():
        raise SystemExit(f"缺少强制要求的美的商用授权字幕字体: {FONT_PATH}")
    font_dst = mat_dir / FONT_PATH.name
    shutil.copyfile(FONT_PATH, font_dst)
    dc_path = draft_dir / "draft_content.json"
    dc_data = json.loads(dc_path.read_text(encoding="utf-8"))
    for tm in dc_data.get("materials", {}).get("texts", []):
        tm["font_path"] = str(font_dst)
        tm["font_title"] = "方正正大黑简体"
        try:
            c_obj = json.loads(tm.get("content", "{}"))
            for st_item in c_obj.get("styles", []):
                st_item["font"] = {"id": "", "path": str(font_dst)}
            tm["content"] = json.dumps(c_obj, ensure_ascii=False)
        except Exception:
            pass
    dc_path.write_text(json.dumps(dc_data, ensure_ascii=False), encoding="utf-8")
    zip_path = dense / f"{draft_name}.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(draft_dir.rglob("*")):
            if f.is_file():
                zf.write(f, f.relative_to(draft_root))
    with zipfile.ZipFile(zip_path) as zf:
        bad = zf.testzip()
        assert bad is None, f"草稿包 CRC 校验失败: {bad}"
    print(f"[pack] 剪映草稿 {draft_dir} + {zip_path}（CRC OK，{len(rows)} 视频段 / {len(stickers)} 花字）")
    return draft_dir, zip_path


def cmd_pack(cfg: dict) -> int:
    work = _work(cfg)
    dense = work / "dense_montage"
    dense.mkdir(parents=True, exist_ok=True)
    _validate_subtitles(cfg["segments"])

    layout = _compute_layout(cfg)
    rows, stickers = layout["rows"], layout["stickers"]
    total_frames, total_dur = layout["duration_frames"], layout["duration_sec"]
    _write_plan(cfg, layout)
    print(f"[pack] 帧布局 {total_frames} 帧 / {total_dur}s")

    # 1) 逐镜 1080x1920@24fps CRF14 重建（禁慢放、禁跨帧混合）
    for r in rows:
        nf = r["frames"]
        frames, meta = _clip_source(cfg, r)
        assert len(frames) == nf, f"Shot {r['index']} 帧数不符: {len(frames)} != {nf}"
        dest = dense / f"video_{r['index']:02d}.mp4"
        rk.write_h264_rawpipe(frames, dest, width=WIDTH, height=HEIGHT, fps=FPS, crf=CRF_LOCK)
        uniform = rk.ensure_uniform_24fps(dest, fps=FPS)
        assert uniform["was_uniform"] and uniform["nb_frames"] == nf, f"Shot {r['index']} 24fps 均匀化失败: {uniform}"
        print(f"[pack] video_{r['index']:02d}.mp4 <- {r['kind']} {nf} 帧 {meta}")
        del frames

    picture = _concat_clips(dense, rows)

    # 2) 画外音轨 + 商业混音
    vo_wav = _build_voiceover(work, rows, total_dur)
    _assert_zero_overlap(vo_wav, rows)
    mix_info = rk.mix_commercial_audio(vo_wav, cfg["bgm"], dense / "mix.m4a", total_dur=total_dur)
    print(f"[pack] mix.m4a: {mix_info}")

    # 3) 字幕（无标点单行 + 62px + y=1320）
    srt_path, ass_path = _write_subtitles(dense, rows)
    print(f"[pack] 字幕 -> {srt_path.name} / {ass_path.name}（{SUB_FONT_SIZE}px, y={SUB_Y}）")

    # 4) 花字 + 字幕烧录成片
    final_mp4 = _burn_final(cfg, picture, dense / "mix.m4a", total_dur, stickers)
    print(f"[pack] 成片 -> {final_mp4}")

    # 5) 5 轨剪映草稿 + 草稿包
    draft_dir, zip_path = _build_draft(cfg, rows, stickers, total_frames, mix_info)

    # 6) 验收：pHash >= 13 + 全片解码零错误
    probe = subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(final_mp4), "-map", "0:v:0", "-map", "0:a:0", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    report = rk.verify_deliverables(cfg["src_video"], final_mp4, draft_dir=draft_dir, phash_min_threshold=PHASH_MIN_GATE)
    report["ffmpeg_decode_ok"] = probe.returncode == 0 and not probe.stderr.strip()
    report["zip_path"] = str(zip_path)
    _dump_json(work / "verify_report.json", report)
    print("[pack] verify: " + json.dumps(report, ensure_ascii=False, indent=2))
    if not report["passed"] or not report["ffmpeg_decode_ok"]:
        print("[pack] 验收未通过，禁止报完成", file=sys.stderr)
        return 1
    print("[pack] 验收通过: pHash/min & 草稿完整 & ffmpeg -xerror 全片零错误")
    return 0


# ============================================================================
# run：prep -> generate -> (全部 success 才) pack
# ============================================================================
def cmd_run(cfg: dict, approve_credits: bool) -> int:
    rc = cmd_prep(cfg, approve_credits)
    if rc != 0:
        return rc
    rc = cmd_generate(cfg, approve_credits)
    if rc != 0:
        print("[run] 生视频未全部成功，停在 generate（不自动重跑，需用户单独批积分）")
        return rc
    jobs = _load_jobs(cfg)
    pending = [s["shot_index"] for s in cfg["segments"]
               if s["kind"] in ("ai", "split") and jobs.get(str(s["shot_index"]), {}).get("status") != "success"]
    if pending:
        print(f"[run] Shot {pending} 尚未生成成功（未传 --approve-credits 时不提交）：停在 generate，未进入 pack")
        return 0
    return cmd_pack(cfg)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="电商带货短视频端到端确定性洗稿状态机（init/prep/generate/pack/run）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"硬锁参数: {MODEL_LOCK} / {RES_LOCK} / {RATIO_LOCK} / {WIDTH}x{HEIGHT}@{FPS}fps / "
               f"字幕 {SUB_FONT_SIZE}px y={SUB_Y} / pHash>= {PHASH_MIN_GATE}",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init", help="检测原子分镜 + 可选原片 ASR + 生成 job.json 模板")
    p_init.add_argument("--src", required=True, help="纯净版原片 MP4")
    p_init.add_argument("--work", required=True, help="工作目录")
    p_init.add_argument("--video-id", default=None, help="默认取工作目录名，用于 /tmp/rewash_<id> 纯 ASCII 目录")
    p_init.add_argument("--head-3v", default=None, help="人物头部三视图")
    p_init.add_argument("--body-3v", default=None, help="人物全身三视图")
    p_init.add_argument("--ref-wav", default=None, help="目标演员参考干声（真声克隆）")
    p_init.add_argument("--bgm", default=None, help="剪映专属 BGM")
    p_init.add_argument("--with-asr", action="store_true", help="逐镜跑 openbmb/VoxCPM-Demo /_run_asr_if_needed -> orig_asr.json")

    p_prep = sub.add_parser("prep", help="导出原子切片 + 全局背景锚点图 + 克隆配音 + 帧预算硬门禁 + 特写去重 + 花字")
    p_prep.add_argument("--config", required=True, help="job.json")
    p_prep.add_argument("--approve-credits", action="store_true", help="非 maestro 档位生成 bg_anchor_2k.png 前必须显式批准")

    p_gen = sub.add_parser("generate", help="积分预审（默认只预览）+ 提交/轮询/落盘/24fps 均匀化")
    p_gen.add_argument("--config", required=True, help="job.json")
    p_gen.add_argument("--approve-credits", action="store_true", help="用户已明确批准积分后才加；不加则 0 提交")

    p_pack = sub.add_parser("pack", help="重建 1080p 成片 + 5 轨剪映草稿 + 端到端验收")
    p_pack.add_argument("--config", required=True, help="job.json")

    p_run = sub.add_parser("run", help="prep -> generate ->（全部 success 才）pack")
    p_run.add_argument("--config", required=True, help="job.json")
    p_run.add_argument("--approve-credits", action="store_true", help="同 generate")

    args = parser.parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args)
    cfg = load_config(args.config)
    if args.cmd == "prep":
        return cmd_prep(cfg, args.approve_credits)
    if args.cmd == "generate":
        return cmd_generate(cfg, args.approve_credits)
    if args.cmd == "pack":
        return cmd_pack(cfg)
    return cmd_run(cfg, args.approve_credits)


if __name__ == "__main__":
    sys.exit(main())
