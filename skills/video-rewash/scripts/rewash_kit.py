#!/usr/bin/env python3
"""
rewash_kit.py — 电商短视频全帧防查重洗稿核心算法工具箱
提供 CLI 与可 import 函数:
  1. sequential-cut : 从第 0 帧顺序解码防 HEVC 随机 seek 串镜
  2. tts            : 纯 Python 免登录剪映逆向 TTS (默认芒果姐姐 zh_female_sistermango)，失败自动降级 edge-tts>=7.0.0
  3. mix-audio      : 320kbps 剪映专属 BGM 自动去片头静音 + 立体声 RMS 定标 + Auto-Ducking 人声闪避混流
  4. stabilize-clip : 全画幅无人物区 LK+RANSAC 大基线刚体稳像 + DIS 24->30fps 光流内插 + 2K 真机浮点 warpAffine 回贴
  5. verify         : 端到端验收 (MD5 + 逐秒 1fps 64-bit DCT pHash 汉明距离 + 音轨响度 + 剪映草稿完整性)
  6. clone-voice    : 免 Key 零样本克隆 (VoxCPM-Demo 首选，失败自动降级 IndexTTS-2.5-Demo)
  7. retime-24fps   : 时间戳抖动/隔帧重复检测与 24fps 均匀 PTS 修复
  8. closeup-rewash : 实拍特写/数据卡零裁边去重
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import shutil
import ssl
import struct
import subprocess
import sys
import time
import urllib.request
import wave
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


# ============================================================================
# 1. 顺序解码零串镜抽帧器 (根治 HEVC B-frame 随机 seek 闪现原片人物)
# ============================================================================
def decode_clip_sequential(
    src_mp4: str | Path,
    ranges_frames: list[tuple[str, int, int]],
    crop_box: tuple[int, int, int, int] | None = None,
) -> dict[str, list[np.ndarray]]:
    """
    从第 0 帧严格顺序解码 src_mp4，一次遍历精确切出多个 [start_frame, end_frame) 区间。
    crop_box: (x0, y0, w, h) 可选无损裁剪框（如去除原片纯净版底部的灰底免责条）。
    """
    max_end = max(ed for _, _, ed in ranges_frames)
    buckets: dict[str, list[np.ndarray]] = {name: [] for name, _, _ in ranges_frames}
    cap = cv2.VideoCapture(str(src_mp4))
    idx = 0
    while idx < max_end:
        ok, frame = cap.read()
        if not ok:
            break
        if crop_box is not None:
            x0, y0, cw, ch = crop_box
            frame = frame[y0 : y0 + ch, x0 : x0 + cw]
        for name, st, ed in ranges_frames:
            if st <= idx < ed:
                buckets[name].append(frame.copy())
        idx += 1
    cap.release()
    return buckets


def detect_atomic_shots(
    src_mp4: str | Path,
    spike_ratio_thresh: float = 3.2,
    local_diff_thresh: float = 14.0,
    min_shot_frames: int = 10,
) -> list[dict]:
    """
    8x8 局部网格 Top-10% 突变率 + 局部时间窗中位数比值切点检测器 (Grid-Max Jump-Cut Detector)。
    根源性解决两个痛点:
      1) 过滤平稳推镜/摇镜/滚筒旋转 (连续运动 local_median 高, spike_ratio ~ 1.0, 零误报);
      2) 100% 捕获背景静止的同机位跳切 Jump Cut (如局部开关舱门跳切、景别微跳切, 全画幅 mean diff 虽低但 Top-10% 网格 spike_ratio > 3.2x)。
    返回每个 100% 纯净原子镜头的起止帧与安全内缩区间。
    """
    cap = cv2.VideoCapture(str(src_mp4))
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    small: list[np.ndarray] = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        small.append(cv2.resize(f, (160, 288), interpolation=cv2.INTER_AREA))
    cap.release()
    if not small:
        return []

    d_local = [0.0]
    for i in range(1, len(small)):
        diff = cv2.absdiff(small[i], small[i - 1]).astype(np.float32)
        cells = diff.reshape(8, 36, 8, 20, 3).mean(axis=(1, 3, 4)).flatten()
        d_local.append(float(np.sort(cells)[-6:].mean()))
    d_arr = np.array(d_local)

    cuts = [0]
    for t in range(1, len(d_arr)):
        win = [d_arr[k] for k in range(max(1, t - 8), min(len(d_arr), t + 9)) if k != t]
        med = float(np.median(win)) if win else 1.5
        ratio = float(d_arr[t] / max(med, 1.8))
        if ratio > spike_ratio_thresh and d_arr[t] > local_diff_thresh:
            if t - cuts[-1] >= min_shot_frames:
                cuts.append(t)
    cuts.append(len(small))

    shots = []
    for idx, (a, b) in enumerate(zip(cuts[:-1], cuts[1:])):
        safe_a = min(a + 2, b - 1)
        safe_b = max(b - 3, safe_a)
        shots.append({
            "shot_index": idx + 1,
            "raw_start_frame": a,
            "raw_end_frame": b - 1,
            "safe_start_frame": safe_a,
            "safe_end_frame": safe_b,
            "num_frames": b - a,
            "duration_sec": round((b - a) / fps, 3),
            "start_sec": round(a / fps, 3),
            "end_sec": round(b / fps, 3),
        })
    return shots


def export_verified_atomic_clip(
    src_mp4: str | Path,
    safe_start_frame: int,
    safe_end_frame: int,
    out_clip_mp4: str | Path,
    out_first_frame_jpg: str | Path | None = None,
    min_duration_sec: float = 2.05,
    spike_ratio_thresh: float = 3.2,
    local_diff_thresh: float = 14.0,
) -> dict:
    """
    从纯净版原片流式直切传给 dreamina multimodal2video 的单镜头原速参考视频 (低内存 <200MB，兼容 3.4K/4K HEVC)。
    内置硬门禁与根源防抖铁律:
      1) 零切点硬门禁 (Hard Gate): 若 [safe_start_frame .. safe_end_frame] 内部存在未拆开的切点或同机位跳切，立即抛出 ValueError 阻断上传!
      2) 零预处理原样直喂: multimodal2video 的输入 --video/--audio 原生支持 2.0~15.0s (仅输出 --duration 最低为 4s)!
         只要单镜 >= 2.05s，100% 保持原片纯净版原帧原速直出，严禁做 Palindrome 正反倒放补尾、严禁 setpts 变速或本地稳像后处理(会导致运镜周期性抽动)!
      3) 仅当极短单镜 < 2.05s 时，仅用最后一帧静态定格 (Freeze Last Frame) 补足至 2.05s 满足 CLI 下限，绝不倒放运镜。
    """
    cap_meta = cv2.VideoCapture(str(src_mp4))
    fps = cap_meta.get(cv2.CAP_PROP_FPS) or 30.0
    src_w = int(cap_meta.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1080
    src_h = int(cap_meta.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1920
    cap_meta.release()

    tw, th = (1080, 1920) if src_h >= src_w else (1920, 1080)
    cmd = [
        "ffmpeg", "-v", "error", "-i", str(src_mp4),
        "-vf", f"trim=start_frame={safe_start_frame}:end_frame={safe_end_frame + 1},setpts=PTS-STARTPTS,scale={tw}:{th}:flags=lanczos",
        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "bgr24", "-",
    ]
    raw = subprocess.check_output(cmd)
    fbytes = tw * th * 3
    n_f = len(raw) // fbytes
    if n_f < 5:
        raise ValueError(f"Clip too short: {n_f} frames")
    arr = np.frombuffer(raw[: n_f * fbytes], dtype=np.uint8).reshape((n_f, th, tw, 3))
    frames = [arr[i] for i in range(n_f)]

    small = [cv2.resize(f, (160, 288), interpolation=cv2.INTER_AREA) for f in frames]
    d_local = [0.0]
    for i in range(1, len(small)):
        diff = cv2.absdiff(small[i], small[i - 1]).astype(np.float32)
        cells = diff.reshape(8, 36, 8, 20, 3).mean(axis=(1, 3, 4)).flatten()
        d_local.append(float(np.sort(cells)[-6:].mean()))
    d_arr = np.array(d_local)

    # Auto-strip 1~2 leading cut-transition residual frames (1.0x native speed preserved)
    lead_trim = 0
    for k_lead in (2, 1):
        if len(d_arr) > k_lead + 5 and float(d_arr[k_lead]) > 18.0:
            lead_trim = k_lead
            break
    if lead_trim > 0:
        frames = frames[lead_trim:] + [frames[-1]] * lead_trim
        small = small[lead_trim:] + [small[-1]] * lead_trim
        d_local = [0.0] + d_local[lead_trim + 1 :] + [0.0] * lead_trim
        d_arr = np.array(d_local)

    for t in range(1, len(d_arr)):
        win = [d_arr[k] for k in range(max(1, t - 8), min(len(d_arr), t + 9)) if k != t]
        med = float(np.median(win)) if win else 1.5
        ratio = float(d_arr[t] / max(med, 1.8))
        if ratio > spike_ratio_thresh and d_arr[t] > local_diff_thresh:
            abs_f = safe_start_frame + t
            raise ValueError(
                f"HARD GATE BLOCKED: Internal cut/jump-cut detected at frame {abs_f} "
                f"(relative idx {t}, D_local={d_arr[t]:.2f}, ratio={ratio:.2f}x) inside [{safe_start_frame}..{safe_end_frame}]! "
                f"Never pass a multi-shot clip to multimodal2video."
            )

    out_clip_mp4 = Path(out_clip_mp4)
    out_clip_mp4.parent.mkdir(parents=True, exist_ok=True)
    if out_first_frame_jpg is not None:
        out_first_frame_jpg = Path(out_first_frame_jpg)
        out_first_frame_jpg.parent.mkdir(parents=True, exist_ok=True)
        cv2.imwrite(str(out_first_frame_jpg), frames[0], [cv2.IMWRITE_JPEG_QUALITY, 97])

    min_frames = int(math.ceil(min_duration_sec * fps))
    out_frames = list(frames)
    while len(out_frames) < min_frames:
        out_frames.append(frames[-1])

    write_h264_rawpipe(out_frames, out_clip_mp4, width=tw, height=th, fps=fps, crf=15)
    return {
        "safe_start_frame": safe_start_frame,
        "safe_end_frame": safe_end_frame,
        "raw_frames": len(frames),
        "valid_frames_24fps": int(round(len(frames) * 24.0 / fps)),
        "exported_frames": len(out_frames),
        "exported_duration_sec": round(len(out_frames) / fps, 3),
        "padded_freeze_frames": len(out_frames) - len(frames),
        "max_local_diff": round(float(d_arr.max()), 2),
    }


def download_dreamina_asset(url: str, out_path: str | Path, is_image: bool = True, submit_id: str | None = None) -> Path:
    """使用 AliDNS DoH 绕过 Fake-IP + 自动刷新 submit_id 避开慢速 p26-dreamina-sign 节点 + TLSv1.2 + 解码完整性校验。"""
    from urllib.parse import urlparse

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    def _is_valid() -> bool:
        if not out_path.exists() or out_path.stat().st_size < 50_000:
            return False
        if is_image:
            try:
                from PIL import Image
                with Image.open(out_path) as pil_im:
                    pil_im.load()
                    return pil_im.width > 200 and pil_im.height > 200
            except Exception:
                return False
        cap = cv2.VideoCapture(str(out_path))
        n_f = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        return n_f >= 20

    if _is_valid():
        return out_path

    def _refresh_url(cur_url: str) -> str:
        if not submit_id:
            return cur_url
        for _ in range(5):
            if "p26-" not in cur_url:
                return cur_url
            try:
                q_out = subprocess.check_output(["dreamina", "query_result", f"--submit_id={submit_id}"], text=True)
                rj = json.loads(q_out).get("result_json", {})
                if is_image and rj.get("images"):
                    cur_url = rj["images"][0].get("image_url", cur_url)
                elif (not is_image) and rj.get("videos"):
                    cur_url = rj["videos"][0].get("video_url", cur_url)
            except Exception:
                break
        return cur_url

    url = _refresh_url(url)

    for attempt in range(8):
        if attempt > 0 and submit_id:
            url = _refresh_url(url)
        host = urlparse(url).hostname or ""
        candidate_ips: list[str] = []
        if host:
            try:
                doh_out = subprocess.check_output(
                    ["curl", "-4", "--noproxy", "*", "-sS", "--connect-timeout", "3", "--max-time", "5", f"https://223.5.5.5/resolve?name={host}&type=A"],
                    text=True,
                )
                doh_json = json.loads(doh_out)
                for a in doh_json.get("Answer", []):
                    ip = str(a.get("data", ""))
                    if a.get("type") == 1 and ip and not ip.startswith("198.18.") and ip not in candidate_ips:
                        candidate_ips.append(ip)
            except Exception:
                pass
        if out_path.exists() and out_path.stat().st_size < 4096:
            out_path.unlink(missing_ok=True)
        resolve_args = ["--resolve", f"{host}:443:{candidate_ips[attempt % len(candidate_ips)]}"] if (host and candidate_ips) else []
        subprocess.run(
            ["curl", "-4", "--noproxy", "*", *resolve_args, "-sS", "-k", "--tlsv1.2", "-C", "-", "--connect-timeout", "5", "--max-time", "30", "-L", url, "-o", str(out_path)],
            check=False,
        )
        if _is_valid():
            return out_path
        if is_image and out_path.exists() and out_path.stat().st_size > 5_000_000:
            out_path.unlink(missing_ok=True)
    raise RuntimeError(f"Failed to download valid asset from {url} -> {out_path}")


def write_h264_rawpipe(
    frames_bgr: Iterable[np.ndarray],
    out_mp4: str | Path,
    width: int = 1080,
    height: int = 1920,
    fps: float = 30.0,
    crf: int = 15,
) -> None:
    """直喂 BGR24 rawvideo 到 libx264，禁止经过 OpenCV mp4v 中间有损编码。"""
    proc = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-f", "rawvideo", "-vcodec", "rawvideo",
            "-s", f"{width}x{height}", "-pix_fmt", "bgr24", "-r", f"{fps}",
            "-i", "-",
            "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(out_mp4), "-loglevel", "error",
        ],
        stdin=subprocess.PIPE,
    )
    assert proc.stdin is not None
    for f in frames_bgr:
        if f.shape[1] != width or f.shape[0] != height:
            f = cv2.resize(f, (width, height), interpolation=cv2.INTER_LANCZOS4)
        proc.stdin.write(f.tobytes())
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise RuntimeError(f"ffmpeg rawvideo encode failed with exit code {rc}: {out_mp4}")


def ensure_uniform_24fps(in_mp4: str | Path, out_mp4: str | Path | None = None, fps: int = 24) -> dict:
    """
    检测时间戳抖动 / 隔帧重复：r_frame_rate == "{fps}/1" 且相邻 pts 抖动 <= 3ms 才算均匀。
    给 out_mp4 时按解码帧 1:1 重打均匀 PTS（ffmpeg settb=AVTB,setpts=N/{fps}/TB）重编码，
    已均匀且路径不同才复制；杜绝 fps 滤镜按原容器标称 fps 转换造成的隔帧重复（实际掉到 12fps）。
    """
    in_mp4 = Path(in_mp4)
    r_frame_rate = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=r_frame_rate", "-of", "csv=p=0", str(in_mp4)],
        text=True,
    ).strip().splitlines()[0]
    pts_out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(in_mp4)],
        text=True,
    )
    pts = [float(x) for x in pts_out.replace(",", "\n").split() if x]
    dt = np.diff(np.array(pts, dtype=np.float64)) if pts else np.array([], dtype=np.float64)
    max_jitter = float(np.max(np.abs(dt - 1.0 / fps))) if len(dt) else 0.0
    was_uniform = (r_frame_rate == f"{fps}/1") and (max_jitter <= 0.003)

    if out_mp4 is not None:
        out_mp4 = Path(out_mp4)
        if not was_uniform:
            out_mp4.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                [
                    "ffmpeg", "-v", "error", "-y", "-i", str(in_mp4),
                    "-map", "0:v:0",
                    "-vf", f"settb=AVTB,setpts=N/{fps}/TB", "-r", str(fps),
                    "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-pix_fmt", "yuv420p", "-an",
                    str(out_mp4),
                ],
                check=True,
            )
        elif in_mp4.resolve() != out_mp4.resolve():
            out_mp4.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(in_mp4, out_mp4)

    return {
        "in_mp4": str(in_mp4),
        "out_mp4": str(out_mp4) if out_mp4 else None,
        "r_frame_rate": r_frame_rate,
        "nb_frames": len(pts),
        "max_pts_jitter_ms": round(max_jitter * 1000, 3),
        "was_uniform": was_uniform,
    }


def universal_closeup_rewash(
    src_frames_1080: list[np.ndarray],
    n_out_24: int,
    shot_idx: int,
    ref_1fps_frames: list[np.ndarray] | None = None,
    sec_indices: list[tuple[int, int]] | None = None,
    target_phash: int = 15,
) -> list[np.ndarray]:
    """
    通用零裁边实拍特写/数据卡去重器 (0° 正立不歪斜、不裁剪四列宽表边缘、零手工坐标):
    结合克制的上下安全区垂直构图微移 + 摄影棚柔光箱方向性光比梯度 + 30->24fps 映射，
    自动按最小档位步进直至逐秒 64-bit DCT pHash 汉明距离 >= target_phash。
    """
    H, W = 1920, 1080
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    xn = (xx / W) - 0.5
    yn = (yy / H) - 0.5
    sign_x = 1.0 if (shot_idx % 2 == 1) else -1.0
    sign_y = -1.0 if ((shot_idx // 2) % 2 == 0) else 1.0
    n_src = len(src_frames_1080)

    candidate: list[np.ndarray] = []
    for step in range(6):
        base_scale = 1.055 + 0.015 * step
        push_delta = 0.025
        v_shift_px = sign_y * (85.0 + 28.0 * step)
        h_shift_px = sign_x * (18.0 + 8.0 * step)
        light_amp = 0.14 + 0.055 * step

        grad = 1.0 + light_amp * (sign_x * 1.15 * xn + sign_y * 1.35 * yn)
        gain_bgr = np.stack([grad * 0.96, grad * 1.00, grad * 1.02], axis=-1).astype(np.float32)

        candidate = []
        for k in range(n_out_24):
            u = k / max(1, n_out_24 - 1)
            idx = min(n_src - 1, max(0, int(round(u * (n_src - 1)))))
            base = src_frames_1080[idx]
            ease = 0.5 - 0.5 * math.cos(math.pi * u)
            sc = base_scale + push_delta * ease
            cx = W * 0.5 + h_shift_px * (1.0 - 0.3 * ease)
            cy = H * 0.5 + v_shift_px * (1.0 - 0.2 * ease)
            M = np.array([[sc, 0.0, (W * 0.5) - sc * cx], [0.0, sc, (H * 0.5) - sc * cy]], dtype=np.float32)
            warped = cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
            candidate.append(np.clip(warped.astype(np.float32) * gain_bgr, 0, 255).astype(np.uint8))

        if not ref_1fps_frames or not sec_indices:
            return candidate
        ok_all = True
        for s_idx, local_f in sec_indices:
            if s_idx < len(ref_1fps_frames) and local_f < len(candidate):
                if int(np.sum(_dct_phash64(ref_1fps_frames[s_idx]) != _dct_phash64(candidate[local_f]))) < target_phash:
                    ok_all = False
                    break
        if ok_all:
            return candidate
    return candidate


# ============================================================================
# 2. 目标演员真声零样本克隆 (VoxCPM 2 首选，IndexTTS-2.5 备选) + 纯 Python 剪映 TTS
# ============================================================================
_VOXCPM_REF_ASR_CACHE: dict[str, str] = {}


def _trim_and_fade_voice(raw_audio_path: str | Path, out_wav_path: str | Path, sr: int = 44100) -> float:
    """1.0x 原速：只切首尾 -38dB 死静音 + 0.012s/0.018s 首尾淡入淡出（严禁 atempo 变速）。返回输出时长秒。"""
    out_wav_path = Path(out_wav_path)
    out_wav_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(raw_audio_path),
            "-af", "silenceremove=start_periods=1:start_threshold=-38dB,areverse,silenceremove=start_periods=1:start_threshold=-38dB,areverse,afade=t=in:st=0:d=0.012,areverse,afade=t=in:st=0:d=0.018,areverse",
            "-ac", "1", "-ar", str(sr), str(out_wav_path), "-loglevel", "error",
        ],
        check=True,
    )
    with wave.open(str(out_wav_path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate())


def _gradio_audio_path(raw_out) -> str:
    """解包 gradio_client 返回: dict{value|path} / list / 裸路径 -> 音频文件路径字符串。"""
    for _ in range(4):
        if isinstance(raw_out, dict):
            raw_out = raw_out.get("value") or raw_out.get("path")
        elif isinstance(raw_out, (list, tuple)):
            raw_out = raw_out[0] if raw_out else None
        else:
            break
    if not raw_out:
        raise RuntimeError("克隆接口未返回音频文件路径")
    return str(raw_out)


def _predict_with_single_retry(call, what: str, cooldown_sec: float):
    """免费容器排队纪律：最多 2 次提交；同一错误连续 2 次即停，禁止原样第三次提交。"""
    last_err = ""
    for _attempt in range(2):
        try:
            return call()
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            same = err == last_err
            last_err = err
            if _attempt == 1 or same:
                raise RuntimeError(f"{what} 连续 2 次失败（同一错误 2 次即停）: {err}") from e
            time.sleep(cooldown_sec)
    raise AssertionError("unreachable")


def _read_back_asr(client, wav_path: str | Path) -> str:
    """调 /_run_asr_if_needed 回读音频文本（5 次内重试，失败返回空串，不阻断成片）。"""
    from gradio_client import handle_file

    for _a in range(5):
        try:
            res = client.predict(checked=True, audio_path=handle_file(str(wav_path)), api_name="/_run_asr_if_needed")
            return res.get("value", "") if isinstance(res, dict) else str(res)
        except Exception:
            time.sleep(2.0)
    return ""


def indextts_clone_segment(
    text_for_tts: str,
    ref_wav_path: str | Path,
    out_wav_path: str | Path = "out.wav",
    sr: int = 44100,
    client=None,
    asr_client=None,
) -> dict:
    """
    免 Key 调用 IndexTeam/IndexTTS-2.5-Demo (/gen_single) 零样本克隆目标演员真声：
    同一参考声同时作为音色 prompt 与情感参考（emo_control_method="Same as the voice reference"），中文 ZH；
    最多 2 次提交、同一错误 2 次即停；统一经 _trim_and_fade_voice 1.0x 裁静音+淡入淡出；
    可选经 asr_client 跑 /_run_asr_if_needed 回读文本，返回时长与识别文本。
    """
    from gradio_client import Client, handle_file

    cl = client or Client("IndexTeam/IndexTTS-2.5-Demo")
    raw_out = _predict_with_single_retry(
        lambda: cl.predict(
            emo_control_method="Same as the voice reference",
            prompt=handle_file(str(ref_wav_path)),
            text=text_for_tts,
            lang_choice="ZH",
            emo_ref_path=handle_file(str(ref_wav_path)),
            api_name="/gen_single",
        ),
        "IndexTTS /gen_single",
        2.0,
    )
    out_wav_path = Path(out_wav_path)
    dur = _trim_and_fade_voice(_gradio_audio_path(raw_out), out_wav_path, sr=sr)
    asr_txt = _read_back_asr(asr_client, out_wav_path) if asr_client is not None else ""
    return {
        "wav_path": str(out_wav_path),
        "duration_sec": round(dur, 3),
        "asr_text": asr_txt,
        "provider": "IndexTTS-2.5-Demo",
    }


def voxcpm_clone_segment(
    text_for_tts: str,
    ref_wav_path: str | Path,
    ref_prompt_text: str | None = None,
    out_wav_path: str | Path = "out.wav",
    cfg_value: float = 2.0,
    sr: int = 44100,
    client=None,
    fallback_indextts: bool = True,
    cooldown_sec: float = 2.0,
) -> dict:
    """
    免 Key 调用 openbmb/VoxCPM-Demo (VoxCPM 2) 零样本克隆目标演员纯净版真声：
    若未传 ref_prompt_text 则自动调 /_run_asr_if_needed 提取并缓存精准参考文本（彻底杜绝音文错位乱码），
    100% 保持 1.0x 原速、仅切除首尾死静音 (严禁 stop_periods=-1 切句中气口、严禁 atempo)，并返回时长与 ASR 校验文本。
    免费容器常排队：/generate 最多 2 次、同一错误 2 次即停（间隔 cooldown_sec）；
    仍失败且 fallback_indextts=True 时自动降级到 IndexTTS-2.5-Demo，否则原样抛出。
    """
    from gradio_client import Client, handle_file

    cl = client or Client("openbmb/VoxCPM-Demo")
    ref_key = str(Path(ref_wav_path).resolve())
    if not ref_prompt_text:
        if ref_key not in _VOXCPM_REF_ASR_CACHE:
            _VOXCPM_REF_ASR_CACHE[ref_key] = _read_back_asr(cl, ref_key)
        ref_prompt_text = _VOXCPM_REF_ASR_CACHE[ref_key]
    try:
        raw_out = _predict_with_single_retry(
            lambda: cl.predict(
                text_input=text_for_tts,
                control_instruction="",
                reference_wav_path_input=handle_file(str(ref_wav_path)),
                use_prompt_text=True,
                prompt_text_input=ref_prompt_text,
                cfg_value_input=cfg_value,
                do_normalize=False,
                denoise=False,
                api_name="/generate",
            ),
            "VoxCPM /generate",
            cooldown_sec,
        )
    except Exception:
        if not fallback_indextts:
            raise
        return indextts_clone_segment(text_for_tts, ref_wav_path, out_wav_path, sr=sr, asr_client=cl)
    out_wav_path = Path(out_wav_path)
    dur = _trim_and_fade_voice(_gradio_audio_path(raw_out), out_wav_path, sr=sr)
    asr_txt = _read_back_asr(cl, out_wav_path)
    return {
        "wav_path": str(out_wav_path),
        "duration_sec": round(dur, 3),
        "asr_text": asr_txt,
        "provider": "VoxCPM-Demo",
    }


def _capcut_fetch_token(timeout: float = 10.0) -> tuple[str, str]:
    url = "https://edit-api-sg.capcut.com/lv/v1/common/tts/token"
    dev_time = str(int(time.time()))
    raw_sig = f"9e2c|s/token|7|5.8.0|{dev_time}||11ac"
    sign = hashlib.md5(raw_sig.encode("utf-8")).hexdigest().lower()
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Appvr": "5.8.0",
            "Device-Time": dev_time,
            "Origin": "https://www.capcut.com",
            "Pf": "7",
            "Sign": sign,
            "Sign-Ver": "1",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/146.0.0.0 Safari/537.36",
            "Content-Length": "0",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    tok = data["data"]["token"]
    app_key = data["data"]["app_key"]
    return tok, app_key


def _ws_recv_exact(sock: ssl.SSLSocket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise EOFError("WebSocket closed unexpectedly")
        buf.extend(chunk)
    return bytes(buf)


def _capcut_ws_synthesize(
    text: str,
    speaker: str = "BV418_streaming",
    speed: int = 10,
    pitch: int = 10,
    volume: int = 10,
    timeout: float = 15.0,
) -> bytes:
    import socket

    token, app_key = _capcut_fetch_token(timeout=timeout)
    host = "sami-sg1.byteintlapi.com"
    path = "/internal/api/v1/ws"
    ctx = ssl.create_default_context()
    raw_sock = socket.create_connection((host, 443), timeout=timeout)
    sock = ctx.wrap_socket(raw_sock, server_hostname=host)
    try:
        ws_key = base64.b64encode(os.urandom(16)).decode("ascii")
        handshake = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {host}\r\n"
            f"Upgrade: websocket\r\n"
            f"Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {ws_key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n"
            f"Origin: https://www.capcut.com\r\n\r\n"
        )
        sock.sendall(handshake.encode("utf-8"))
        resp_hdr = b""
        while b"\r\n\r\n" not in resp_hdr:
            c = sock.recv(1)
            if not c:
                raise RuntimeError("WebSocket handshake failed")
            resp_hdr += c
        if b"101" not in resp_hdr.splitlines()[0]:
            raise RuntimeError(f"WebSocket upgrade rejected: {resp_hdr[:120]!r}")

        payload = {
            "text": text,
            "speaker": speaker,
            "pitch": pitch,
            "speed": speed,
            "volume": volume,
            "rate": 24000,
            "appid": "348188",
        }
        msg_bytes = json.dumps(
            {
                "token": token,
                "appkey": app_key,
                "namespace": "TTS",
                "event": "StartTask",
                "payload": json.dumps(payload, ensure_ascii=False),
            },
            ensure_ascii=False,
        ).encode("utf-8")

        # 发送 masked text frame (opcode=0x81)
        mask_key = os.urandom(4)
        length = len(msg_bytes)
        header = bytearray([0x81])
        if length < 126:
            header.append(0x80 | length)
        elif length < 65536:
            header.append(0x80 | 126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(0x80 | 127)
            header.extend(struct.pack("!Q", length))
        header.extend(mask_key)
        masked = bytes(b ^ mask_key[i & 3] for i, b in enumerate(msg_bytes))
        sock.sendall(bytes(header) + masked)

        audio_chunks = bytearray()
        while True:
            b0, b1 = _ws_recv_exact(sock, 2)
            opcode = b0 & 0x0F
            masked_srv = (b1 & 0x80) != 0
            plen = b1 & 0x7F
            if plen == 126:
                plen = struct.unpack("!H", _ws_recv_exact(sock, 2))[0]
            elif plen == 127:
                plen = struct.unpack("!Q", _ws_recv_exact(sock, 8))[0]
            mkey = _ws_recv_exact(sock, 4) if masked_srv else b""
            data = _ws_recv_exact(sock, plen)
            if masked_srv:
                data = bytes(x ^ mkey[i & 3] for i, x in enumerate(data))

            if opcode == 0x8:  # Close
                break
            if opcode == 0x9:  # Ping -> Pong
                pong = bytearray([0x8A, 0x80]) + os.urandom(4)
                sock.sendall(bytes(pong))
                continue
            try:
                evt = json.loads(data.decode("utf-8"))
                if evt.get("event") == "TaskFinished":
                    break
                sc = evt.get("status_code", 20000000)
                if evt.get("event") == "TaskFailed" or (sc != 20000000 and sc >= 400):
                    raise RuntimeError(f"CapCut TTS failed: {evt}")
            except UnicodeDecodeError:
                audio_chunks.extend(data)

        if len(audio_chunks) < 200:
            raise RuntimeError("CapCut TTS returned empty audio buffer")
        return bytes(audio_chunks)
    finally:
        sock.close()


def synthesize_tts(
    text: str,
    out_wav: str | Path,
    speaker: str = "BV418_streaming",
    speed: int = 10,
    sample_rate: int = 44100,
    trim_silence: bool = True,
    max_dur_sec: float | None = None,
) -> float:
    """
    合成单句口播为标准单声道 16-bit WAV 并返回去首尾静音后精确秒数。
    优先走火山/剪映原生音色 (默认火山直播一姐 BV418_streaming, speed=10 原速)，异常自动降级 uvx edge-tts>=7.0.0。
    仅裁剪句首与句尾空白 (不截断句内字间辅音气口，防止吞字抢拍)，并在指定 max_dur_sec 时微调语速使其 100% 落入分镜槽位。
    """
    out_wav = Path(out_wav)
    raw_tmp = out_wav.with_suffix(".raw_tts.bin")
    try:
        audio_bytes = _capcut_ws_synthesize(text=text, speaker=speaker, speed=speed)
        raw_tmp.write_bytes(audio_bytes)
    except Exception as exc:
        print(f"[TTS fallback -> edge-tts>=7.0.0] reason: {exc}", file=sys.stderr)
        subprocess.run(
            [
                "uvx", "--from", "edge-tts>=7.0.0", "edge-tts",
                "--voice", "zh-CN-XiaoyiNeural", "--rate=+5%",
                "--text", text, "--write-media", str(raw_tmp),
            ],
            check=True,
        )

    af = (
        "silenceremove=start_periods=1:start_silence=0.03:start_threshold=-45dB,"
        "areverse,silenceremove=start_periods=1:start_silence=0.05:start_threshold=-45dB,areverse"
        if trim_silence
        else "anull"
    )
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(raw_tmp),
            "-af", af, "-ar", str(sample_rate), "-ac", "1", "-c:a", "pcm_s16le",
            str(out_wav), "-loglevel", "error",
        ],
        check=True,
    )
    raw_tmp.unlink(missing_ok=True)
    with wave.open(str(out_wav), "rb") as wf:
        dur = wf.getnframes() / float(sample_rate)

    if max_dur_sec is not None and dur > max_dur_sec > 0.2:
        ratio = min(1.35, dur / max_dur_sec)
        fit_tmp = out_wav.with_suffix(".fit.wav")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(out_wav),
                "-af", f"atempo={ratio:.4f}",
                "-ar", str(sample_rate), "-ac", "1", "-c:a", "pcm_s16le",
                str(fit_tmp), "-loglevel", "error",
            ],
            check=True,
        )
        fit_tmp.replace(out_wav)
        with wave.open(str(out_wav), "rb") as wf:
            dur = wf.getnframes() / float(sample_rate)
    return dur


# ============================================================================
# 3. 立体声商业混音器 (自动切 BGM 片头静音 + RMS 定标 + Auto-Ducking 人声闪避)
# ============================================================================
def mix_commercial_audio(
    vo_wav: str | Path,
    bgm_mp3: str | Path,
    out_m4a: str | Path,
    total_dur: float,
    sfx_wav: str | Path | None = None,
    sr: int = 44100,
    gap_db: float = -20.5,
    duck_ratio: float = 0.41,
) -> dict[str, float]:
    """
    双声道立体声商业混音:
      - 自动裁剪 BGM 片头空白，从首个乐音点入拍
      - BGM 气口定标 gap_db (-20.5 dBFS)，人声说话时自动闪避至约 -25 dBFS
      - 输出 192kbps 双声道 AAC (.m4a)
    """
    n_samples = int(round(total_dur * sr))
    tmp_bgm = Path(f"/tmp/_rewash_bgm_{os.getpid()}.wav")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(bgm_mp3),
            "-ar", str(sr), "-ac", "2", "-c:a", "pcm_s16le",
            str(tmp_bgm), "-loglevel", "error",
        ],
        check=True,
    )

    def _read_st(p: Path) -> np.ndarray:
        with wave.open(str(p), "rb") as wf:
            ch = wf.getnchannels()
            arr = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
            arr = arr.reshape(-1, 2) if ch == 2 else np.stack([arr, arr], axis=1)
        return arr

    raw_bgm = _read_st(tmp_bgm)
    tmp_bgm.unlink(missing_ok=True)
    nz = np.where(np.max(np.abs(raw_bgm), axis=1) > 0.025)[0]
    st_idx = max(0, int(nz[0]) - int(0.05 * sr)) if len(nz) > 0 else 0
    bgm_st = raw_bgm[st_idx : st_idx + n_samples]
    while len(bgm_st) < n_samples:
        bgm_st = np.vstack([bgm_st, raw_bgm[: n_samples - len(bgm_st)]])

    def _fit_len(arr: np.ndarray) -> np.ndarray:
        if len(arr) < n_samples:
            return np.vstack([arr, np.zeros((n_samples - len(arr), 2), dtype=np.float32)])
        return arr[:n_samples]

    vo_st = _fit_len(_read_st(Path(vo_wav)))
    sfx_st = _fit_len(_read_st(Path(sfx_wav))) if sfx_wav and Path(sfx_wav).exists() else np.zeros((n_samples, 2), dtype=np.float32)

    bgm_rms = float(np.sqrt(np.mean(bgm_st[int(0.4 * sr) : max(int(1.0 * sr), n_samples - int(1.5 * sr))] ** 2)))
    bgm_norm = bgm_st * ((10.0 ** (gap_db / 20.0)) / (bgm_rms + 1e-8))

    vo_env = np.abs(vo_st[:, 0])
    w1, w2 = int(0.10 * sr), int(0.18 * sr)
    speaking = np.clip(np.convolve(vo_env, np.ones(w1, dtype=np.float32) / w1, mode="same") / 0.035, 0.0, 1.0)
    speaking = np.convolve(speaking, np.ones(w2, dtype=np.float32) / w2, mode="same")
    duck_gain = 1.0 - duck_ratio * speaking

    fade = np.ones(n_samples, dtype=np.float32)
    fade[: int(0.30 * sr)] = np.linspace(0.25, 1.0, int(0.30 * sr))
    fade[-int(1.10 * sr) :] = np.linspace(1.0, 0.04, int(1.10 * sr))

    bgm_final = bgm_norm * (duck_gain * fade)[:, None]
    vo_final = vo_st / (float(np.max(np.abs(vo_st))) + 1e-8) * 0.86
    sfx_final = sfx_st * 0.48

    mix = np.clip(vo_final + bgm_final + sfx_final, -0.97, 0.97)
    tmp_master = Path(f"/tmp/_rewash_master_{os.getpid()}.wav")
    with wave.open(str(tmp_master), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes((mix * 32767.0).astype(np.int16).tobytes())

    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(tmp_master),
            "-c:a", "aac", "-b:a", "192k", "-ar", str(sr), "-ac", "2",
            str(out_m4a), "-loglevel", "error",
        ],
        check=True,
    )
    tmp_master.unlink(missing_ok=True)

    act = speaking > 0.4
    vo_db = float(20 * np.log10(np.sqrt(np.mean(vo_final[act] ** 2)) + 1e-9)) if np.any(act) else -99.0
    bgm_spk_db = float(20 * np.log10(np.sqrt(np.mean(bgm_final[act] ** 2)) + 1e-9)) if np.any(act) else -99.0
    return {
        "bgm_trimmed_sec": round(st_idx / sr, 3),
        "vo_active_dbfs": round(vo_db, 2),
        "bgm_speaking_dbfs": round(bgm_spk_db, 2),
    }


# ============================================================================
# 4. 全画幅大基线刚体稳像 + 原生 24fps 零重影映射 + 分镜专属 2K 底板 B_i 像素级分区锁死
# ============================================================================
def _safe_similarity_step(
    gray_src: np.ndarray,
    gray_dst: np.ndarray,
    mask: np.ndarray | None = None,
    max_corners: int = 450,
    reproj_thresh: float = 1.5,
) -> np.ndarray:
    """安全估计两帧间的纯缩放+平移刚体矩阵 (3x3)，特征不足或 RANSAC 失败时自动回退为单位阵。"""
    pts = cv2.goodFeaturesToTrack(gray_src, maxCorners=max_corners, qualityLevel=0.008, minDistance=7, mask=mask)
    if pts is None or len(pts) < 4:
        return np.eye(3, dtype=np.float64)
    p2, st, _ = cv2.calcOpticalFlowPyrLK(gray_src, gray_dst, pts, None, winSize=(23, 23), maxLevel=4)
    if p2 is None or st is None:
        return np.eye(3, dtype=np.float64)
    good = st.flatten() == 1
    if int(np.sum(good)) < 4:
        return np.eye(3, dtype=np.float64)
    q0 = pts[good].reshape(-1, 2)
    q1 = p2[good].reshape(-1, 2)
    M12, _ = cv2.estimateAffinePartial2D(q0, q1, method=cv2.RANSAC, ransacReprojThreshold=reproj_thresh)
    if M12 is None:
        return np.eye(3, dtype=np.float64)
    sc = float(np.hypot(M12[0, 0], M12[0, 1]))
    if not (0.85 <= sc <= 1.18):
        return np.eye(3, dtype=np.float64)
    return np.array([[sc, 0.0, float(M12[0, 2])], [0.0, sc, float(M12[1, 2])], [0.0, 0.0, 1.0]], dtype=np.float64)


def stabilize_and_paste_product(
    raw_frames_720: list[np.ndarray],
    anchor_2k_bgr: np.ndarray,
    product_box_1080: tuple[int, int, int, int],
    person_bg_mask_720: np.ndarray | None = None,
    target_frames_30fps: int | None = None,
    anchor_frame_idx: int = 0,
    poly_deg: int = 4,
    overscan: float = 1.000,
    static_lock_mask_1080: np.ndarray | None = None,
    dynamic_exclude_masks_1080: list[np.ndarray] | None = None,
    use_frame_blending: bool = False,
) -> list[np.ndarray]:
    """
    消除 Seedance 24fps VAE 锯齿抖动并 100% 浮点亚像素锁死分镜专属 2K 底板 B_i (背景柜体+真机):
      - 修复 Bug 1: Step A 严格传入 person_bg_mask_720 过滤人物动态特征，并对 None/退化矩阵提供单位阵回退保护
      - 修复 Bug 2: 默认 overscan=1.000，严禁 1.045x 盲目放大破坏分镜真实焦距 Z_i
      - 修复 Bug 3: 默认原生 24.0fps 1:1 整数帧映射 (use_frame_blending=False)，彻底根除 30fps addWeighted 跨帧半透明重影
      - 修复 Bug 4: 支持 static_lock_mask_1080 (同时锁死无遮挡背景柜体与真机区) 并排除动态手部/开门区 M_dyn(t) (16px 余弦羽化)
    """
    W, H = 1080, 1920
    n_src = len(raw_frames_720)
    if n_src == 0:
        return []
    if target_frames_30fps is None:
        target_frames_30fps = n_src
    if anchor_frame_idx < 0 or anchor_frame_idx >= n_src:
        anchor_frame_idx = 0

    frames_720 = [
        cv2.resize(f, (720, 1280), interpolation=cv2.INTER_AREA) if (f.shape[1], f.shape[0]) != (720, 1280) else f
        for f in raw_frames_720
    ]
    ref720 = cv2.resize(anchor_2k_bgr, (720, 1280), interpolation=cv2.INTER_AREA)
    gray_ref = cv2.cvtColor(ref720, cv2.COLOR_BGR2GRAY)
    grays = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in frames_720]

    # Step A: 在锚点帧静态背景区与 ref720 间建立基准变换 (严格使用 person_bg_mask_720 屏蔽人物)
    M3_anc = _safe_similarity_step(grays[anchor_frame_idx], gray_ref, mask=person_bg_mask_720, max_corners=500, reproj_thresh=1.5)

    # Step B: 全画幅无人物区大基线前后递推刚体链 (纯缩放+平移，零旋转杠杆抖动)
    M3_to_ref: list[np.ndarray] = [np.eye(3, dtype=np.float64) for _ in range(n_src)]
    M3_to_ref[anchor_frame_idx] = M3_anc

    for i in range(anchor_frame_idx - 1, -1, -1):
        M3_to_ref[i] = M3_to_ref[i + 1] @ _safe_similarity_step(grays[i], grays[i + 1], mask=person_bg_mask_720, reproj_thresh=1.2)
    for i in range(anchor_frame_idx + 1, n_src):
        M3_to_ref[i] = M3_to_ref[i - 1] @ _safe_similarity_step(grays[i], grays[i - 1], mask=person_bg_mask_720, reproj_thresh=1.2)

    meas = []
    for i in range(n_src):
        Minv = np.linalg.inv(M3_to_ref[i])
        meas.append([Minv[0, 0], Minv[0, 2], Minv[1, 2]])
    meas_arr = np.array(meas, dtype=np.float64)

    deg = min(poly_deg, max(1, n_src - 1))
    t_src = np.linspace(0.0, 1.0, n_src)
    ps = np.polyfit(t_src, meas_arr[:, 0], deg)
    ptx = np.polyfit(t_src, meas_arr[:, 1], deg)
    pty = np.polyfit(t_src, meas_arr[:, 2], deg)

    cx0, cy0 = 360.0 * (1.0 - overscan), 640.0 * (1.0 - overscan)
    M3_over = np.array([[overscan, 0.0, cx0], [0.0, overscan, cy0], [0.0, 0.0, 1.0]], dtype=np.float64)

    stab_720 = []
    for i in range(n_src):
        s_t, tx_t, ty_t = float(np.polyval(ps, t_src[i])), float(np.polyval(ptx, t_src[i])), float(np.polyval(pty, t_src[i]))
        M3_targ = M3_over @ np.array([[s_t, 0.0, tx_t], [0.0, s_t, ty_t], [0.0, 0.0, 1.0]], dtype=np.float64)
        M_corr = (M3_targ @ M3_to_ref[i])[:2, :].astype(np.float32)
        stab_720.append(cv2.warpAffine(frames_720[i], M_corr, (720, 1280), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE))

    # Step C: 默认原生 24fps 1:1 整数帧映射 (彻底禁用 addWeighted 跨帧半透明重影) + 分镜专属 2K 底板 B_i 分区锁死
    if static_lock_mask_1080 is not None:
        base_lock_1080 = static_lock_mask_1080.astype(np.float32)
        if base_lock_1080.max() > 1.5:
            base_lock_1080 /= 255.0
    else:
        px0, py0, px1, py1 = product_box_1080
        base_lock_1080 = np.zeros((H, W), dtype=np.float32)
        base_lock_1080[py0:py1, px0:px1] = 1.0
    base_lock_1080 = cv2.GaussianBlur(base_lock_1080, (0, 0), 8.0)

    S1080 = np.diag([1.5, 1.5, 1.0])
    S720 = np.diag([1.0 / 1.5, 1.0 / 1.5, 1.0])
    K_2K = anchor_2k_bgr.shape[1] / float(W)

    flows_f, flows_b = [], []
    if use_frame_blending and target_frames_30fps != n_src and n_src > 1:
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        stab_g = [cv2.cvtColor(f, cv2.COLOR_BGR2GRAY) for f in stab_720]
        for i in range(n_src - 1):
            flows_f.append(dis.calc(stab_g[i], stab_g[i + 1], None))
            flows_b.append(dis.calc(stab_g[i + 1], stab_g[i], None))
    gy, gx = np.mgrid[0:1280, 0:720].astype(np.float32)

    out_1080: list[np.ndarray] = []
    t_out = np.linspace(0.0, 1.0, target_frames_30fps)
    for k, tk in enumerate(t_out):
        pos = tk * (n_src - 1)
        idx_near = min(n_src - 1, max(0, int(round(pos))))
        if not use_frame_blending or target_frames_30fps == n_src or n_src == 1:
            f720 = stab_720[idx_near]
        else:
            i0 = min(n_src - 2, int(math.floor(pos)))
            alpha = pos - i0
            if alpha < 1e-4:
                f720 = stab_720[i0]
            elif alpha > 1.0 - 1e-4:
                f720 = stab_720[i0 + 1]
            else:
                w0 = cv2.remap(stab_720[i0], gx - alpha * flows_b[i0][:, :, 0], gy - alpha * flows_b[i0][:, :, 1], cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
                w1 = cv2.remap(stab_720[i0 + 1], gx - (1.0 - alpha) * flows_f[i0][:, :, 0], gy - (1.0 - alpha) * flows_f[i0][:, :, 1], cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
                f720 = cv2.addWeighted(w0, 1.0 - alpha, w1, alpha, 0.0)

        up = cv2.resize(cv2.bilateralFilter(f720, d=5, sigmaColor=10, sigmaSpace=10), (W, H), interpolation=cv2.INTER_LANCZOS4)
        s_k, tx_k, ty_k = float(np.polyval(ps, tk)), float(np.polyval(ptx, tk)), float(np.polyval(pty, tk))
        M3_1080 = S1080 @ M3_over @ np.array([[s_k, 0.0, tx_k], [0.0, s_k, ty_k], [0.0, 0.0, 1.0]], dtype=np.float64) @ S720
        M_1080 = M3_1080[:2, :].astype(np.float32)
        M_2k = M_1080.copy()
        M_2k[:, :2] /= K_2K
        hd_2k = cv2.warpAffine(anchor_2k_bgr, M_2k, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)

        cur_lock = base_lock_1080
        if dynamic_exclude_masks_1080 is not None and idx_near < len(dynamic_exclude_masks_1080):
            dyn_m = dynamic_exclude_masks_1080[idx_near].astype(np.float32)
            if dyn_m.max() > 1.5:
                dyn_m /= 255.0
            dyn_m = cv2.GaussianBlur(dyn_m, (0, 0), 8.0)
            cur_lock = cur_lock * np.clip(1.0 - dyn_m, 0.0, 1.0)

        w_mask = cv2.warpAffine(cur_lock, M_1080, (W, H), flags=cv2.INTER_LINEAR)[..., None]
        comp = (hd_2k.astype(np.float32) * w_mask + up.astype(np.float32) * (1.0 - w_mask)).clip(0, 255).astype(np.uint8)
        out_1080.append(comp)
    return out_1080


def stabilize_and_lock_scene_24fps(
    frames_1080: list[np.ndarray],
    plate_2k_bgr: np.ndarray,
    static_zone_mask_1080: np.ndarray,
    dynamic_protect_mask_1080: np.ndarray | None = None,
    feather_sigma: float = 10.0,
    track_camera: bool = False,
    track_mask_1080: np.ndarray | None = None,
) -> list[np.ndarray]:
    """
    原生 24.0fps 分镜专属 2K 底板 B_i 零漂移像素锁死器 (Zero Frame-Blending, Zero Geometric Drift):
      - 将 1440x2560 分镜母板 B_i (plate_2k_bgr) 对齐至 1080x1920 画面
      - 在 static_zone_mask_1080 指定的静态柜体与无遮挡真机区内，自动检测并排除运动手部/人物/开门区 M_dyn(t)
      - 以 16px 余弦/高斯羽化平滑融合，既保证柜体与真机 0.0px 几何锁死，又杜绝人物边缘发丝光晕与 30fps 重影
    """
    W, H = 1080, 1920
    if not frames_1080:
        return []
    plate_1080 = cv2.resize(plate_2k_bgr, (W, H), interpolation=cv2.INTER_AREA).astype(np.float32)
    stat_m = static_zone_mask_1080.astype(np.float32)
    if stat_m.max() > 1.5:
        stat_m /= 255.0
    if dynamic_protect_mask_1080 is not None:
        dyn_p = dynamic_protect_mask_1080.astype(np.float32)
        if dyn_p.max() > 1.5:
            dyn_p /= 255.0
        stat_m = stat_m * np.clip(1.0 - dyn_p, 0.0, 1.0)
    stat_m_blur = cv2.GaussianBlur(stat_m, (0, 0), feather_sigma)[..., None]

    g_ref = cv2.cvtColor(frames_1080[0], cv2.COLOR_BGR2GRAY)
    pts_ref = None
    if track_camera:
        tm = track_mask_1080 if track_mask_1080 is not None else (stat_m > 0.5).astype(np.uint8) * 255
        pts_ref = cv2.goodFeaturesToTrack(g_ref, maxCorners=400, qualityLevel=0.01, minDistance=8, mask=tm)

    out: list[np.ndarray] = []
    for f in frames_1080:
        f_1080 = cv2.resize(f, (W, H), interpolation=cv2.INTER_LANCZOS4) if (f.shape[1], f.shape[0]) != (W, H) else f
        cur_plate = plate_1080
        cur_mask = stat_m_blur
        if track_camera and pts_ref is not None and len(pts_ref) >= 4:
            g_cur = cv2.cvtColor(f_1080, cv2.COLOR_BGR2GRAY)
            p_cur, st, _ = cv2.calcOpticalFlowPyrLK(g_ref, g_cur, pts_ref, None, winSize=(23, 23), maxLevel=4)
            if p_cur is not None and st is not None and int(np.sum(st.flatten() == 1)) >= 4:
                M, _ = cv2.estimateAffinePartial2D(
                    pts_ref[st.flatten() == 1].reshape(-1, 2),
                    p_cur[st.flatten() == 1].reshape(-1, 2),
                    method=cv2.RANSAC,
                    ransacReprojThreshold=1.8,
                )
                if M is not None:
                    cur_plate = cv2.warpAffine(plate_1080, M, (W, H), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
                    cur_mask = cv2.warpAffine(stat_m_blur[:, :, 0], M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0.0)[..., None]
        comp = (cur_plate * cur_mask + f_1080.astype(np.float32) * (1.0 - cur_mask)).clip(0, 255).astype(np.uint8)
        out.append(comp)
    return out


# ============================================================================
# 5. 端到端防查重与交付完整性核验 (Oracle)
# ============================================================================
def _dct_phash64(bgr: np.ndarray) -> np.ndarray:
    g = cv2.resize(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY), (32, 32)).astype(np.float32)
    dct = cv2.dct(g)[:8, :8].flatten()
    med = np.median(dct[1:])
    return dct > med


def verify_deliverables(
    orig_mp4: str | Path,
    new_mp4: str | Path,
    draft_dir: str | Path | None = None,
    phash_min_threshold: int = 13,
) -> dict:
    """
    端到端防查重验收（阈值 > 12，按 SKILL.md 严格门槛默认 13）：
    pHash 同时给逐秒对齐距离与移位无关的最近源帧距离，重排时间轴时以最近源距离为准。
    """
    orig_mp4, new_mp4 = Path(orig_mp4), Path(new_mp4)
    md5_orig = hashlib.md5(orig_mp4.read_bytes()).hexdigest()
    md5_new = hashlib.md5(new_mp4.read_bytes()).hexdigest()

    def _sample_1fps(p: Path) -> list[np.ndarray]:
        cap = cv2.VideoCapture(str(p))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames, idx, next_t = [], 0, 0.5
        while True:
            ok, f = cap.read()
            if not ok:
                break
            if (idx / fps) >= next_t:
                frames.append(f)
                next_t += 1.0
            idx += 1
        cap.release()
        return frames

    f_orig = _sample_1fps(orig_mp4)
    f_new = _sample_1fps(new_mp4)
    n_cmp = min(len(f_orig), len(f_new))
    h_orig = [_dct_phash64(f) for f in f_orig]
    h_new = [_dct_phash64(f) for f in f_new]
    dists_aligned = [int(np.sum(h_new[k] != h_orig[k])) for k in range(n_cmp)]
    # 移位无关：每帧新成片只与最近的源帧比（全片洗完重排时间轴时对齐逐秒不可用）
    dists_nearest = [min(int(np.sum(hn != ho)) for ho in h_orig) for hn in h_new] if (h_orig and h_new) else []

    vol_proc = subprocess.run(
        ["ffmpeg", "-i", str(new_mp4), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    mean_vol = None
    for ln in vol_proc.stderr.splitlines():
        if "mean_volume:" in ln:
            mean_vol = float(ln.split("mean_volume:")[1].split()[0])

    draft_info = None
    if draft_dir is not None and Path(draft_dir).exists():
        dc_path = Path(draft_dir) / "draft_content.json"
        dc = json.loads(dc_path.read_text(encoding="utf-8"))
        mats = dc.get("materials", {}).get("videos", []) + dc.get("materials", {}).get("audios", [])
        import re as _re
        def _resolve_mat(p_raw: str) -> Path:
            rel = _re.sub(r"^##_draftpath_placeholder_[^#]*##/", "", p_raw)
            return (Path(draft_dir) / rel) if rel != p_raw else Path(p_raw)
        missing = [m["path"] for m in mats if not _resolve_mat(m["path"]).exists()]
        draft_info = {
            "tracks": len(dc.get("tracks", [])),
            "materials": len(mats),
            "missing_files": len(missing),
        }

    passed = (
        md5_orig != md5_new
        and len(dists_nearest) > 0
        and min(dists_nearest) >= phash_min_threshold
        and (mean_vol is not None and -28.0 <= mean_vol <= -8.0)
        and (draft_info is None or draft_info["missing_files"] == 0)
    )
    return {
        "passed": passed,
        "md5_distinct": md5_orig != md5_new,
        "seconds_compared": n_cmp,
        "phash_min": min(dists_nearest) if dists_nearest else 0,
        "phash_aligned_min": min(dists_aligned) if dists_aligned else 0,
        "phash_mean": round(float(np.mean(dists_nearest)), 2) if dists_nearest else 0.0,
        "phash_max": max(dists_nearest) if dists_nearest else 0,
        "audio_mean_volume_db": mean_vol,
        "jianying_draft": draft_info,
    }


# ============================================================================
# 6. 多变无黑框综艺种草立体花字库 (12款造型 × 7款正版潮字 × 4种灵动入场动效)
# ============================================================================
VARIETY_STYLES = (
    "model_yellow",     # 1. 斜切荧光黄马克笔高光条 (LTTeHei 斜切) - 型号/系列卡
    "burst_orange",     # 2. 元气亮橙 3D 粗字 + 8根金黄放射光芒线 (LTTeHei) - 核心卖点炸场
    "arrow_red",        # 3. 纯白粗字鲜红发光包边 + 3D 上升红箭头 (HanZhen) - 99.99%/数据飙升
    "check_blue",       # 4. 翠绿白边圆勾章 + 双层冰蓝 3D 字 (ZhengDaHei) - 烘干/实测达标
    "bubble_aqua",      # 5. Q弹圆体冰川蓝渐变 + 6颗晶透高光水珠泡泡 (HuPo) - 气泡水/活水漂洗
    "sparkle_gold",     # 6. 香槟暖金渐变字 + 摩卡棕3D底 + 四角星芒✦ (TeCuGuangHui) - 奢护/羊毛绿标
    "lightning_cyan",   # 7. 立体金黄闪电徽章 + 机甲宽体电光青3D字 (YaZhuTe) - AI智洗/快洗/超薄
    "shield_emerald",   # 8. 翡翠绿十字护盾徽章 + 森绿双层3D字 (LTTeHei) - 母婴级/双水路/除螨
    "crown_berry",      # 9. 左上斜戴金黄小皇冠 + 樱花粉白渐变莓果紫厚边 (HuPo) - 内衣专洗/女神种草
    "stamp_vermilion",  # 10. 微倾朱砂红圆角印章 + 琥珀金橙3D主字 (ShangKu) - 硬核实测/免晾晒
    "split_highlight",  # 11. 柠檬黄+纯白双色碰撞字 + 珊瑚红厚边波点装饰 (ShangKu) - 痛点终结/解放双手
    "tech_lime",        # 12. 得意黑斜体荧光青柠渐变 + 极夜蓝厚边双斜杠// (SmileySans) - 静音分贝/变频科技
)


def _vgrad_rgba(size: tuple[int, int], top_rgba: tuple[int, int, int, int], bot_rgba: tuple[int, int, int, int], y0: int, y1: int):
    from PIL import Image
    w, h = size
    ys = np.clip((np.arange(h, dtype=np.float32) - y0) / max(1.0, float(y1 - y0)), 0.0, 1.0)[:, None]
    t = np.array(top_rgba, dtype=np.float32)[None, None, :]
    b = np.array(bot_rgba, dtype=np.float32)[None, None, :]
    arr = np.broadcast_to((t * (1.0 - ys[:, :, None]) + b * ys[:, :, None]), (h, w, 4)).astype(np.uint8)
    return Image.fromarray(arr, mode="RGBA")


def _draw_grad_text(size: tuple[int, int], pos: tuple[int, int], text: str, fnt, top_rgb: tuple[int, int, int], bot_rgb: tuple[int, int, int]):
    from PIL import Image, ImageDraw
    mask_im = Image.new("L", size, 0)
    md = ImageDraw.Draw(mask_im)
    bb = md.textbbox(pos, text, font=fnt)
    md.text(pos, text, font=fnt, fill=255)
    grad = _vgrad_rgba(size, (*top_rgb, 255), (*bot_rgb, 255), bb[1], bb[3])
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    out.paste(grad, (0, 0), mask_im)
    return out


def _draw_four_star(draw, cx: int, cy: int, r_outer: int, r_inner: int, fill, outline=None, width: int = 1):
    pts = []
    for k in range(8):
        ang = k * math.pi / 4.0 - math.pi / 2.0
        r = r_outer if k % 2 == 0 else r_inner
        pts.append((cx + math.cos(ang) * r, cy + math.sin(ang) * r))
    draw.polygon(pts, fill=fill, outline=outline, width=width)


def render_variety_sticker(
    style: str,
    text: str,
    out_png: str | Path,
    fonts_root: str | Path = "/home/zd/src/ai-mixcut/assets/fonts",
    scale: float = 1.28,
) -> Path:
    """
    3x 超采样抗锯齿渲染 12 款无黑框综艺种草立体花字（默认 1.28x 醒目大号商业花字）。
    严禁使用死板半透明黑框胶囊；全部采用多层圆润厚描边 + 3D 立体底托 + 精致微装饰。
    """
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    out_png = Path(out_png)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    froot = Path(fonts_root)
    FONT_MAP = {
        "tehei": froot / "midea_fonts/FZLTTHJW.TTF",
        "hanzhen": froot / "midea_fonts/FZHZGBJW_0.TTF",
        "zhengda": froot / "midea_fonts/FZZDHJW.TTF",
        "hupo": froot / "midea_fonts/FZHPJW.TTF",
        "guanghui": froot / "midea_fonts/FZTCGHJW_0.TTF",
        "yazhu": froot / "midea_fonts/FZYaZTJ_Te.TTF",
        "shangku": froot / "midea_fonts/FZSHANGKJW.TTF",
        "smiley": froot / "SmileySans-Oblique.ttf",
    }
    def _fnt(key: str, px: int):
        if len(text) > 9:
            px = max(36, int(round(px * 9.0 / len(text))))
        p = FONT_MAP.get(key, FONT_MAP["tehei"])
        if not p.exists():
            p = FONT_MAP["tehei"]
        f = ImageFont.truetype(str(p), px)
        try:
            ImageDraw.Draw(Image.new("RGBA", (8, 8))).textbbox((0, 0), text, font=f)
            return f
        except OSError:
            return ImageFont.truetype(str(FONT_MAP["tehei"]), px)

    S = 3
    if style not in VARIETY_STYLES:
        style = "burst_orange"

    def _save_hi(im_hi: Image.Image) -> None:
        bbox = im_hi.split()[3].getbbox()
        eff_scale = scale
        if bbox is not None:
            vis_w = (bbox[2] - bbox[0]) / S * eff_scale
            if vis_w > 860:
                eff_scale *= 860.0 / vis_w
        tw_o = max(1, int(round(im_hi.width / S * eff_scale)))
        th_o = max(1, int(round(im_hi.height / S * eff_scale)))
        im_scaled = im_hi.resize((tw_o, th_o), Image.Resampling.LANCZOS)
        ab = im_scaled.split()[3].getbbox()
        if ab is not None:
            pad_y = 20
            y0, y1 = max(0, ab[1] - pad_y), min(th_o, ab[3] + pad_y)
            crop_w = ab[2] - ab[0]
            crop_h = y1 - y0
            sub = im_scaled.crop((ab[0], y0, ab[2], y1))
            canvas = Image.new("RGBA", (max(1080, crop_w + 40), crop_h), (0, 0, 0, 0))
            canvas.paste(sub, ((canvas.width - crop_w) // 2, 0))
            if canvas.width > 1080:
                canvas = canvas.resize((1080, int(round(crop_h * 1080 / canvas.width))), Image.Resampling.LANCZOS)
            canvas.save(out_png)
        else:
            im_scaled.save(out_png)

    if style == "model_yellow":
        cw, ch = 860 * S, 200 * S
        fnt = _fnt("tehei", 66 * S)
        tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        bb = tmp.textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx, ty = (cw - tw) // 2 - bb[0], (ch - th) // 2 - bb[1] - 6 * S
        bar_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bar_layer)
        x1, x2 = (cw - tw) // 2 - 8 * S, (cw + tw) // 2 + 12 * S
        y_bot = (ch + th) // 2 + 10 * S
        y_top = y_bot - 36 * S
        bd.rounded_rectangle([x1 - 14*S, y_top - 10*S, x2 + 14*S, y_bot + 14*S], radius=20*S, fill=(255, 255, 255, 255))
        bd.rounded_rectangle([x1, y_top, x2, y_bot], radius=10*S, fill=(255, 226, 24, 255))
        txt_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(txt_layer).text((tx, ty), text, font=fnt, fill=(255, 255, 255, 255), stroke_width=18*S, stroke_fill=(255, 255, 255, 255))
        fg_layer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(fg_layer).text((tx, ty), text, font=fnt, fill=(20, 24, 33, 255))
        comp = Image.alpha_composite(Image.alpha_composite(bar_layer, txt_layer), fg_layer)
        comp = comp.transform((cw, ch), Image.Transform.AFFINE, (1, 0.15, -15*S, 0, 1, 0), resample=Image.Resampling.BICUBIC)
        sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        sh.paste(Image.new("RGBA", (cw, ch), (0, 0, 0, 95)), (4*S, 7*S), comp.split()[3].filter(ImageFilter.GaussianBlur(8*S)))
        _save_hi(Image.alpha_composite(sh, comp))

    elif style == "burst_orange":
        cw, ch = 820 * S, 220 * S
        fnt = _fnt("tehei", 78 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx, ty = (cw - tw) // 2 - bb[0], (ch - th) // 2 - bb[1] + 4 * S
        sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((tx + 5*S, ty + 8*S), text, font=fnt, fill=(98, 30, 8, 225), stroke_width=20*S, stroke_fill=(98, 30, 8, 225))
        sh = sh.filter(ImageFilter.GaussianBlur(2 * S))
        stroke = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(stroke).text((tx, ty), text, font=fnt, fill=(255, 255, 255, 255), stroke_width=17*S, stroke_fill=(255, 255, 255, 255))
        fg = _draw_grad_text((cw, ch), (tx, ty), text, fnt, (255, 138, 36), (228, 68, 22))
        ray = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        rd = ImageDraw.Draw(ray)
        lx, rx, cy = (cw - tw) // 2 - 34*S, (cw + tw) // 2 + 34*S, ch // 2 + 6*S
        for p0, p1 in [
            ((lx - 12*S, cy - 26*S), (lx - 54*S, cy - 48*S)), ((lx - 14*S, cy + 2*S), (lx - 60*S, cy + 2*S)),
            ((lx - 12*S, cy + 30*S), (lx - 54*S, cy + 52*S)), ((rx + 12*S, cy - 26*S), (rx + 54*S, cy - 48*S)),
            ((rx + 14*S, cy + 2*S), (rx + 60*S, cy + 2*S)), ((rx + 12*S, cy + 30*S), (rx + 54*S, cy + 52*S)),
            ((cw//2 - 115*S, ty - 6*S), (cw//2 - 135*S, ty - 44*S)), ((cw//2 + 115*S, ty - 6*S), (cw//2 + 135*S, ty - 44*S)),
        ]:
            rd.line([p0, p1], fill=(95, 50, 0, 155), width=11*S)
            rd.line([p0, p1], fill=(255, 216, 42, 255), width=7*S)
        _save_hi(Image.alpha_composite(Image.alpha_composite(Image.alpha_composite(sh, ray), stroke), fg))

    elif style == "arrow_red":
        cw, ch = 900 * S, 210 * S
        fnt = _fnt("hanzhen", 70 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        total_w = tw + 114 * S
        tx, ty = (cw - total_w) // 2 - bb[0], (ch - th) // 2 - bb[1] + 4 * S
        glow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(glow).text((tx, ty + 5*S), text, font=fnt, fill=(135, 12, 12, 225), stroke_width=23*S, stroke_fill=(150, 15, 15, 225))
        glow = glow.filter(ImageFilter.GaussianBlur(7 * S))
        fg = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(fg).text((tx, ty), text, font=fnt, fill=(255, 255, 255, 255), stroke_width=14*S, stroke_fill=(235, 42, 34, 255))
        ar_im = Image.new("RGBA", (180*S, 200*S), (0, 0, 0, 0))
        ImageDraw.Draw(ar_im).polygon([(90*S,18*S),(142*S,74*S),(108*S,74*S),(108*S,172*S),(72*S,172*S),(72*S,74*S),(38*S,74*S)], fill=(238,44,36,255), outline=(255,255,255,245), width=5*S)
        ar_rot = ar_im.rotate(-26, resample=Image.Resampling.BICUBIC)
        ar_sh = Image.new("RGBA", ar_rot.size, (0, 0, 0, 0))
        ar_sh.paste(Image.new("RGBA", ar_rot.size, (90, 10, 10, 145)), (3*S, 5*S), ar_rot.split()[3].filter(ImageFilter.GaussianBlur(4*S)))
        fg.alpha_composite(Image.alpha_composite(ar_sh, ar_rot), ((cw - total_w) // 2 + tw + 2*S, ch//2 - 98*S))
        _save_hi(Image.alpha_composite(glow, fg))

    elif style == "check_blue":
        cw, ch = 820 * S, 200 * S
        fnt = _fnt("zhengda", 74 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        icon_d, gap = 96 * S, 36 * S
        sx, cy = (cw - (icon_d + gap + tw)) // 2, ch // 2
        ic_sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(ic_sh).ellipse([sx + 3*S, cy - icon_d//2 + 6*S, sx + icon_d + 3*S, cy + icon_d//2 + 6*S], fill=(10, 40, 20, 135))
        ic_sh = ic_sh.filter(ImageFilter.GaussianBlur(5 * S))
        ic = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        idraw = ImageDraw.Draw(ic)
        idraw.ellipse([sx, cy - icon_d//2, sx + icon_d, cy + icon_d//2], fill=(44, 204, 78, 255), outline=(255, 255, 255, 255), width=7*S)
        idraw.line([(sx + 24*S, cy + 3*S), (sx + 43*S, cy + 22*S), (sx + 74*S, cy - 16*S)], fill=(255, 255, 255, 255), width=11*S, joint="curve")
        tx, ty = sx + icon_d + gap - bb[0], cy - th // 2 - bb[1]
        deep_sh = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(deep_sh).text((tx + 5*S, ty + 8*S), text, font=fnt, fill=(20, 80, 150, 240), stroke_width=19*S, stroke_fill=(20, 80, 150, 240))
        fg = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(fg).text((tx, ty), text, font=fnt, fill=(255, 255, 255, 255), stroke_width=15*S, stroke_fill=(58, 156, 248, 255))
        _save_hi(Image.alpha_composite(Image.alpha_composite(Image.alpha_composite(ic_sh, deep_sh), ic), fg))

    elif style == "bubble_aqua":
        cw, ch = 840 * S, 220 * S
        fnt = _fnt("hupo", 78 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx, ty = (cw - tw) // 2 - bb[0], (ch - th) // 2 - bb[1] + 4 * S
        deep = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(deep).text((tx + 5*S, ty + 8*S), text, font=fnt, fill=(12, 72, 128, 235), stroke_width=22*S, stroke_fill=(12, 72, 128, 235))
        deep = deep.filter(ImageFilter.GaussianBlur(2 * S))
        mid = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(mid).text((tx, ty), text, font=fnt, fill=(255, 255, 255, 255), stroke_width=17*S, stroke_fill=(255, 255, 255, 255))
        fg = _draw_grad_text((cw, ch), (tx, ty), text, fnt, (20, 185, 245), (18, 118, 226))
        bub = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bub)
        lx, rx, cy = (cw - tw) // 2, (cw + tw) // 2, ch // 2
        for bx, by, br in [
            (lx - 38*S, cy - 20*S, 21*S), (lx - 16*S, cy + 28*S, 13*S), (lx + 30*S, cy - 58*S, 11*S),
            (rx + 36*S, cy - 16*S, 23*S), (rx + 14*S, cy + 32*S, 14*S), (rx - 40*S, cy - 56*S, 10*S),
        ]:
            bd.ellipse([bx - br, by - br, bx + br, by + br], fill=(135, 228, 255, 150), outline=(255, 255, 255, 245), width=4*S)
            hr = max(3*S, br // 3)
            bd.ellipse([bx - br//2, by - br//2, bx - br//2 + hr, by - br//2 + hr], fill=(255, 255, 255, 245))
        comp = Image.alpha_composite(Image.alpha_composite(deep, mid), fg)
        _save_hi(Image.alpha_composite(comp, bub))

    elif style == "sparkle_gold":
        cw, ch = 860 * S, 220 * S
        fnt = _fnt("guanghui", 74 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx, ty = (cw - tw) // 2 - bb[0], (ch - th) // 2 - bb[1] + 4 * S
        outer = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(outer).text((tx + 3*S, ty + 5*S), text, font=fnt, fill=(255, 252, 240, 245), stroke_width=22*S, stroke_fill=(255, 252, 240, 250))
        mid = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(mid).text((tx, ty), text, font=fnt, fill=(82, 42, 8, 255), stroke_width=14*S, stroke_fill=(82, 42, 8, 255))
        fg = _draw_grad_text((cw, ch), (tx, ty), text, fnt, (255, 236, 128), (232, 162, 28))
        deep = outer
        st = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st)
        lx, rx, cy = (cw - tw) // 2, (cw + tw) // 2, ch // 2
        for scx, scy, sr in [(lx - 36*S, cy - 22*S, 26*S), (rx + 36*S, cy - 18*S, 28*S), (rx + 12*S, cy + 32*S, 15*S), (lx - 14*S, cy + 28*S, 14*S)]:
            _draw_four_star(sd, scx + 2*S, scy + 3*S, sr, sr // 4, fill=(90, 52, 10, 160))
            _draw_four_star(sd, scx, scy, sr, sr // 4, fill=(255, 236, 120, 255), outline=(255, 255, 255, 255), width=3*S)
        comp = Image.alpha_composite(Image.alpha_composite(deep, mid), fg)
        _save_hi(Image.alpha_composite(comp, st))

    elif style == "lightning_cyan":
        cw, ch = 880 * S, 210 * S
        fnt = _fnt("yazhu", 68 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        iw, gap = 82 * S, 26 * S
        sx, cy = (cw - (iw + gap + tw)) // 2, ch // 2
        tx, ty = sx + iw + gap - bb[0], cy - th // 2 - bb[1]
        deep = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(deep).text((tx + 6*S, ty + 9*S), text, font=fnt, fill=(10, 36, 68, 245), stroke_width=20*S, stroke_fill=(10, 36, 68, 245))
        fg = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(fg).text((tx, ty), text, font=fnt, fill=(255, 255, 255, 255), stroke_width=15*S, stroke_fill=(0, 188, 232, 255))
        bolt = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        bd = ImageDraw.Draw(bolt)
        bpts = [
            (sx + 48*S, cy - 58*S), (sx + 8*S, cy + 4*S), (sx + 38*S, cy + 4*S),
            (sx + 22*S, cy + 60*S), (sx + 76*S, cy - 8*S), (sx + 44*S, cy - 8*S),
        ]
        bd.polygon([(x + 4*S, y + 6*S) for x, y in bpts], fill=(12, 36, 68, 210))
        bd.polygon(bpts, fill=(255, 218, 28, 255), outline=(255, 255, 255, 255), width=6*S)
        _save_hi(Image.alpha_composite(Image.alpha_composite(deep, fg), bolt))

    elif style == "shield_emerald":
        cw, ch = 860 * S, 210 * S
        fnt = _fnt("tehei", 72 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        iw, gap = 90 * S, 32 * S
        sx, cy = (cw - (iw + gap + tw)) // 2, ch // 2
        tx, ty = sx + iw + gap - bb[0], cy - th // 2 - bb[1]
        deep = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(deep).text((tx + 5*S, ty + 8*S), text, font=fnt, fill=(10, 68, 46, 240), stroke_width=19*S, stroke_fill=(10, 68, 46, 240))
        fg = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(fg).text((tx, ty), text, font=fnt, fill=(255, 255, 255, 255), stroke_width=15*S, stroke_fill=(32, 182, 118, 255))
        shd = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shd)
        cx_i = sx + iw // 2
        spts = [
            (cx_i, cy - 52*S), (sx + iw - 4*S, cy - 36*S), (sx + iw - 8*S, cy + 10*S),
            (cx_i, cy + 54*S), (sx + 8*S, cy + 10*S), (sx + 4*S, cy - 36*S),
        ]
        sd.polygon([(x + 3*S, y + 6*S) for x, y in spts], fill=(10, 55, 36, 175))
        sd.polygon(spts, fill=(36, 196, 122, 255), outline=(255, 255, 255, 255), width=6*S)
        sd.rounded_rectangle([cx_i - 7*S, cy - 22*S, cx_i + 7*S, cy + 22*S], radius=4*S, fill=(255, 255, 255, 255))
        sd.rounded_rectangle([cx_i - 22*S, cy - 7*S, cx_i + 22*S, cy + 7*S], radius=4*S, fill=(255, 255, 255, 255))
        _save_hi(Image.alpha_composite(Image.alpha_composite(deep, fg), shd))

    elif style == "crown_berry":
        cw, ch = 880 * S, 245 * S
        fnt = _fnt("hupo", 74 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        tx, ty = (cw - tw) // 2 - bb[0] + 14 * S, (ch - th) // 2 - bb[1] + 22 * S
        deep = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(deep).text((tx + 5*S, ty + 8*S), text, font=fnt, fill=(92, 18, 68, 235), stroke_width=21*S, stroke_fill=(92, 18, 68, 235))
        mid = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(mid).text((tx, ty), text, font=fnt, fill=(255, 255, 255, 255), stroke_width=16*S, stroke_fill=(226, 68, 148, 255))
        fg = _draw_grad_text((cw, ch), (tx, ty), text, fnt, (255, 255, 255), (255, 224, 240))
        cr = Image.new("RGBA", (120*S, 96*S), (0, 0, 0, 0))
        cd = ImageDraw.Draw(cr)
        cpts = [(20*S, 72*S), (12*S, 28*S), (42*S, 48*S), (60*S, 16*S), (78*S, 48*S), (108*S, 28*S), (100*S, 72*S)]
        cd.polygon([(x + 2*S, y + 4*S) for x, y in cpts], fill=(92, 18, 68, 160))
        cd.polygon(cpts, fill=(255, 212, 38, 255), outline=(255, 255, 255, 255), width=5*S)
        for px, py in [(12*S, 24*S), (60*S, 13*S), (108*S, 24*S)]:
            cd.ellipse([px - 6*S, py - 6*S, px + 6*S, py + 6*S], fill=(255, 242, 130, 255), outline=(255, 255, 255, 255), width=3*S)
        cr_rot = cr.rotate(22, resample=Image.Resampling.BICUBIC, expand=True)
        comp = Image.alpha_composite(Image.alpha_composite(deep, mid), fg)
        top_glyph_y = ty + bb[1]
        left_glyph_x = tx + bb[0]
        comp.alpha_composite(cr_rot, (max(2*S, left_glyph_x - 68*S), max(0, top_glyph_y - 68*S)))
        _save_hi(comp)

    elif style == "stamp_vermilion":
        badge_txt, main_txt = ("实测", text)
        if "|" in text:
            sp = text.split("|", 1)
            badge_txt, main_txt = sp[0].strip() or "实测", sp[1].strip()
        cw, ch = 880 * S, 215 * S
        fnt = _fnt("shangku", 72 * S)
        bfnt = _fnt("tehei", 36 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), main_txt, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        bw, bh, gap = 118 * S, 68 * S, 22 * S
        sx, cy = (cw - (bw + gap + tw)) // 2, ch // 2
        tx, ty = sx + bw + gap - bb[0], cy - th // 2 - bb[1]
        deep = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(deep).text((tx + 5*S, ty + 8*S), main_txt, font=fnt, fill=(96, 36, 8, 240), stroke_width=20*S, stroke_fill=(96, 36, 8, 240))
        mid = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(mid).text((tx, ty), main_txt, font=fnt, fill=(255, 252, 240, 255), stroke_width=15*S, stroke_fill=(238, 122, 28, 255))
        st_im = Image.new("RGBA", (160*S, 120*S), (0, 0, 0, 0))
        sd = ImageDraw.Draw(st_im)
        rx0, ry0 = 20*S, 24*S
        sd.rounded_rectangle([rx0 + 3*S, ry0 + 5*S, rx0 + bw + 3*S, ry0 + bh + 5*S], radius=16*S, fill=(90, 20, 10, 165))
        sd.rounded_rectangle([rx0, ry0, rx0 + bw, ry0 + bh], radius=16*S, fill=(228, 46, 36, 255), outline=(255, 255, 255, 255), width=6*S)
        bbb = sd.textbbox((0, 0), badge_txt, font=bfnt)
        sd.text((rx0 + (bw - (bbb[2]-bbb[0]))//2 - bbb[0], ry0 + (bh - (bbb[3]-bbb[1]))//2 - bbb[1]), badge_txt, font=bfnt, fill=(255, 255, 255, 255))
        st_rot = st_im.rotate(8, resample=Image.Resampling.BICUBIC)
        comp = Image.alpha_composite(deep, mid)
        comp.alpha_composite(st_rot, (sx - 18*S, cy - 60*S))
        _save_hi(comp)

    elif style == "split_highlight":
        if "|" in text:
            p1, p2 = text.split("|", 1)
        else:
            cut = min(3, max(2, len(text) // 2))
            p1, p2 = text[:cut], text[cut:]
        cw, ch = 880 * S, 215 * S
        fnt = _fnt("shangku", 74 * S)
        tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        b1 = tmp.textbbox((0, 0), p1, font=fnt)
        b2 = tmp.textbbox((0, 0), p2, font=fnt) if p2 else (0, 0, 0, 0)
        w1, w2 = b1[2] - b1[0], (b2[2] - b2[0] if p2 else 0)
        gap = 8 * S if p2 else 0
        tw = w1 + gap + w2
        th = max(b1[3] - b1[1], (b2[3] - b2[1] if p2 else 0))
        sx, ty = (cw - tw) // 2, (ch - th) // 2 - b1[1] + 4 * S
        x1, x2 = sx - b1[0], sx + w1 + gap - (b2[0] if p2 else 0)
        deep = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        dd = ImageDraw.Draw(deep)
        dd.text((x1 + 5*S, ty + 8*S), p1, font=fnt, fill=(92, 22, 26, 240), stroke_width=20*S, stroke_fill=(92, 22, 26, 240))
        if p2:
            dd.text((x2 + 5*S, ty + 8*S), p2, font=fnt, fill=(92, 22, 26, 240), stroke_width=20*S, stroke_fill=(92, 22, 26, 240))
        fg = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        fd = ImageDraw.Draw(fg)
        fd.text((x1, ty), p1, font=fnt, fill=(255, 236, 52, 255), stroke_width=15*S, stroke_fill=(232, 66, 62, 255))
        if p2:
            fd.text((x2, ty), p2, font=fnt, fill=(255, 255, 255, 255), stroke_width=15*S, stroke_fill=(232, 66, 62, 255))
        rx_edge = sx + tw + 18 * S
        fd.ellipse([rx_edge, ty - 6*S, rx_edge + 20*S, ty + 14*S], fill=(255, 232, 56, 255), outline=(255, 255, 255, 255), width=4*S)
        fd.ellipse([rx_edge + 18*S, ty + 16*S, rx_edge + 31*S, ty + 29*S], fill=(255, 118, 108, 255), outline=(255, 255, 255, 255), width=3*S)
        _save_hi(Image.alpha_composite(deep, fg))

    else:  # tech_lime
        cw, ch = 860 * S, 210 * S
        fnt = _fnt("smiley", 80 * S)
        bb = ImageDraw.Draw(Image.new("RGBA", (10, 10))).textbbox((0, 0), text, font=fnt)
        tw, th = bb[2] - bb[0], bb[3] - bb[1]
        total_w = tw + 64 * S
        tx, ty = (cw - total_w) // 2 - bb[0], (ch - th) // 2 - bb[1] + 2 * S
        outer_w = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(outer_w).text((tx + 3*S, ty + 5*S), text, font=fnt, fill=(255, 255, 255, 235), stroke_width=23*S, stroke_fill=(255, 255, 255, 245))
        navy = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        ImageDraw.Draw(navy).text((tx, ty), text, font=fnt, fill=(18, 28, 48, 255), stroke_width=16*S, stroke_fill=(18, 28, 48, 255))
        fg = _draw_grad_text((cw, ch), (tx, ty), text, fnt, (206, 255, 56), (92, 238, 118))
        sl = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        sd = ImageDraw.Draw(sl)
        bx = (cw - total_w) // 2 + tw + 18 * S
        cy = ch // 2
        for off in (0, 24 * S):
            pts = [(bx + off + 16*S, cy - 38*S), (bx + off + 30*S, cy - 38*S), (bx + off + 8*S, cy + 38*S), (bx + off - 6*S, cy + 38*S)]
            sd.polygon(pts, fill=(182, 255, 62, 255), outline=(18, 28, 48, 255), width=5*S)
        comp = Image.alpha_composite(Image.alpha_composite(outer_w, navy), fg)
        _save_hi(Image.alpha_composite(comp, sl))

    return out_png


def pick_variety_styles(texts: list[str], seed: int = 0) -> list[str]:
    """
    按文案卖点语义匹配最佳花字造型池，并确保同一条视频内 100% 零重款；
    不同视频传入不同 seed 即可自动错位轮换风格组合，告别千篇一律。
    """
    used: set[str] = set()
    chosen: list[str] = []
    for idx, raw in enumerate(texts):
        t = raw.upper()
        if any(ch.isalpha() for ch in t) and any(ch.isdigit() for ch in t) and "%" not in t and "DB" not in t:
            pool = ["model_yellow", "tech_lime", "lightning_cyan"]
        elif "%" in t or "率" in t or "飙" in t or "倍" in t or "洗净比" in t:
            pool = ["arrow_red", "stamp_vermilion", "burst_orange"]
        elif any(k in t for k in ("泡", "水", "漂", "净", "渍", "溶")):
            pool = ["bubble_aqua", "burst_orange", "lightning_cyan"]
        elif any(k in t for k in ("内衣", "丝", "柔", "护", "羊毛", "奢")):
            pool = ["crown_berry", "sparkle_gold", "shield_emerald"]
        elif any(k in t for k in ("菌", "螨", "母婴", "健康", "防交叉", "独立")):
            pool = ["shield_emerald", "arrow_red", "sparkle_gold"]
        elif any(k in t for k in ("DB", "分贝", "静", "降噪", "快", "智", "AI", "变频")):
            pool = ["tech_lime", "lightning_cyan", "check_blue"]
        elif any(k in t for k in ("烘", "干", "免晾", "实测")):
            pool = ["check_blue", "stamp_vermilion", "sparkle_gold"]
        else:
            pool = ["split_highlight", "burst_orange", "sparkle_gold", "stamp_vermilion"]

        rot = (seed + idx) % len(pool)
        ordered = pool[rot:] + pool[:rot] + list(VARIETY_STYLES)
        for cand in ordered:
            if cand not in used:
                used.add(cand)
                chosen.append(cand)
                break
    return chosen


def overlay_variety_sticker(
    frame_bgr: np.ndarray,
    sticker_bgra: np.ndarray,
    cx: int,
    cy: int,
    progress_frames: float,
    anim_mode: str = "jelly_pop",
) -> np.ndarray:
    """
    支持 4 种综艺灵动入场动效 (默认在 8~10 帧内完成弹入):
      - 'jelly_pop':    0.35 -> 1.12 -> 0.97 -> 1.00 果冻Q弹
      - 'tilt_snap':    微倾 -7° -> +2° -> 0° 俏皮摆正 + 缩放
      - 'slide_spring': 下方 42px 弹簧上浮落位
      - 'pulse_pop':    弹入后带轻微呼吸律动
    """
    if progress_frames < 0:
        return frame_bgr
    p = max(0.0, float(progress_frames))
    scale, dy, deg, alpha_gain = 1.0, 0, 0.0, 1.0

    if anim_mode == "tilt_snap":
        if p < 9.0:
            u = p / 9.0
            scale = 0.4 + 0.6 * (1.0 - (1.0 - u) ** 3)
            deg = -8.0 * math.cos(u * math.pi * 1.35) * (1.0 - u)
            alpha_gain = min(1.0, p / 3.0)
    elif anim_mode == "slide_spring":
        if p < 9.0:
            u = p / 9.0
            dy = int(round(44.0 * ((1.0 - u) ** 2) * math.cos(u * math.pi * 1.25)))
            scale = 0.82 + 0.18 * min(1.0, u * 1.3)
            alpha_gain = min(1.0, p / 3.5)
    elif anim_mode == "pulse_pop":
        if p < 7.0:
            u = p / 7.0
            scale = 0.35 + 0.75 * math.sin(u * math.pi * 0.65)
            alpha_gain = min(1.0, p / 2.5)
        else:
            scale = 1.0 + 0.022 * math.sin((p - 7.0) * 0.22)
    else:  # jelly_pop
        if p < 5.0:
            scale = 0.35 + 0.77 * (p / 5.0)
            alpha_gain = min(1.0, p / 2.5)
        elif p < 9.0:
            scale = 1.12 - 0.12 * ((p - 5.0) / 4.0)

    work = sticker_bgra
    sh, sw = work.shape[:2]
    if abs(deg) > 0.25:
        M = cv2.getRotationMatrix2D((sw / 2.0, sh / 2.0), deg, 1.0)
        work = cv2.warpAffine(work, M, (sw, sh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))
    nw, nh = max(2, int(round(sw * scale))), max(2, int(round(sh * scale)))
    if (nw, nh) != (sw, sh):
        work = cv2.resize(work, (nw, nh), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR)

    H, W = frame_bgr.shape[:2]
    x0, y0 = cx - nw // 2, cy - nh // 2 + dy
    x1, y1 = max(0, x0), max(0, y0)
    x2, y2 = min(W, x0 + nw), min(H, y0 + nh)
    if x2 <= x1 or y2 <= y1:
        return frame_bgr
    sub = work[y1 - y0 : y2 - y0, x1 - x0 : x2 - x0]
    a = (sub[:, :, 3:4].astype(np.float32) / 255.0) * alpha_gain
    roi = frame_bgr[y1:y2, x1:x2].astype(np.float32)
    frame_bgr[y1:y2, x1:x2] = np.clip(sub[:, :, :3].astype(np.float32) * a + roi * (1.0 - a), 0, 255).astype(np.uint8)
    return frame_bgr


def main() -> None:
    parser = argparse.ArgumentParser(description="电商带货短视频全帧洗稿工具箱")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_det = sub.add_parser("detect-shots", help="8x8 局部网格 Top-10%% 突变率检测全片 100%% 纯净原子镜头 (含同机位跳切)")
    p_det.add_argument("--src", required=True, help="原片 MP4 路径")

    p_exp = sub.add_parser("export-atomic-clip", help="带零切点硬门禁 (Hard Gate) 导出单镜头参考视频与真正首帧图")
    p_exp.add_argument("--src", required=True, help="原片 MP4 路径")
    p_exp.add_argument("--start", type=int, required=True, help="safe_start_frame")
    p_exp.add_argument("--end", type=int, required=True, help="safe_end_frame")
    p_exp.add_argument("--out-clip", required=True, help="输出参考视频 MP4 路径")
    p_exp.add_argument("--out-first-frame", default=None, help="可选输出真正第1帧 JPG 路径 (供生成每镜首帧同态 2K 锚点图)")

    p_tts = sub.add_parser("tts", help="剪映原生音色 TTS 合成单句 WAV")
    p_tts.add_argument("--text", required=True)
    p_tts.add_argument("--out", required=True)
    p_tts.add_argument("--speaker", default="BV418_streaming")
    p_tts.add_argument("--speed", type=int, default=11)

    p_clone = sub.add_parser("clone-voice", help="免 Key 零样本克隆目标演员真声单句 WAV (VoxCPM -> IndexTTS 自动降级)")
    p_clone.add_argument("--text", required=True, help="要合成的口播文本（不加标点）")
    p_clone.add_argument("--ref-wav", required=True, help="目标演员参考干声 (同时作音色 prompt / 情感参考)")
    p_clone.add_argument("--ref-text", default=None, help="参考干声文本；不传则自动 ASR 提取并缓存")
    p_clone.add_argument("--out", required=True, help="输出单声道 44.1kHz WAV")
    p_clone.add_argument("--no-fallback", action="store_true", help="VoxCPM 失败时不再降级到 IndexTTS")

    p_mix = sub.add_parser("mix-audio", help="立体声 BGM 自动去静音 + 人声闪避混音")
    p_mix.add_argument("--vo", required=True)
    p_mix.add_argument("--bgm", required=True)
    p_mix.add_argument("--sfx", default=None)
    p_mix.add_argument("--dur", type=float, required=True)
    p_mix.add_argument("--out", required=True)

    p_stk = sub.add_parser("sticker", help="渲染 12 款无黑框综艺种草立体花字 PNG")
    p_stk.add_argument("--style", default="auto", help="款式名或 auto")
    p_stk.add_argument("--text", required=True)
    p_stk.add_argument("--out", required=True)
    p_stk.add_argument("--seed", type=int, default=0)

    p_rt = sub.add_parser("retime-24fps", help="检测并修复时间戳抖动/隔帧重复：按帧数 1:1 重打均匀 PTS")
    p_rt.add_argument("--src", required=True, help="待检查/修复的 MP4")
    p_rt.add_argument("--out", default=None, help="输出 MP4；不传则只检测不写文件")
    p_rt.add_argument("--fps", type=int, default=24)

    p_cu = sub.add_parser("closeup-rewash", help="实拍特写/数据卡零裁边去重 (universal_closeup_rewash 封装)")
    p_cu.add_argument("--src", required=True, help="源镜头 MP4 (1080x1920)")
    p_cu.add_argument("--out", required=True, help="输出无损重编码 MP4")
    p_cu.add_argument("--n-out", type=int, required=True, help="n_out_24: 输出帧数（24fps 计）")
    p_cu.add_argument("--shot-idx", type=int, required=True, help="shot_idx: 决定推拉/光比方向")
    p_cu.add_argument("--ref", default=None, help="可选原片 MP4，逐秒抽帧作 ref_1fps_frames")
    p_cu.add_argument("--sec-indices", default=None, help="可选 sec:local 对，逗号分隔，如 3:12,4:20")
    p_cu.add_argument("--target-phash", type=int, default=15)
    p_cu.add_argument("--crf", type=int, default=14)

    p_ver = sub.add_parser("verify", help="端到端防查重与草稿完整性校验")
    p_ver.add_argument("--orig", required=True)
    p_ver.add_argument("--new", required=True)
    p_ver.add_argument("--draft", default=None)
    p_ver.add_argument("--phash-min", type=int, default=13, help="逐秒 64-bit pHash 汉明距离最小值门槛（SKILL.md 要求 > 12）")

    args = parser.parse_args()
    if args.cmd == "detect-shots":
        shots = detect_atomic_shots(args.src)
        print(json.dumps(shots, ensure_ascii=False, indent=2))
    elif args.cmd == "export-atomic-clip":
        res = export_verified_atomic_clip(args.src, args.start, args.end, args.out_clip, args.out_first_frame)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "tts":
        dur = synthesize_tts(args.text, args.out, speaker=args.speaker, speed=args.speed)
        print(json.dumps({"out": args.out, "duration_sec": round(dur, 3)}, ensure_ascii=False))
    elif args.cmd == "clone-voice":
        res = voxcpm_clone_segment(
            args.text,
            args.ref_wav,
            ref_prompt_text=args.ref_text,
            out_wav_path=args.out,
            fallback_indextts=not args.no_fallback,
        )
        print(json.dumps(res, ensure_ascii=False, indent=2))
    elif args.cmd == "mix-audio":
        res = mix_commercial_audio(args.vo, args.bgm, args.out, total_dur=args.dur, sfx_wav=args.sfx)
        print(json.dumps(res, ensure_ascii=False))
    elif args.cmd == "sticker":
        st = pick_variety_styles([args.text], seed=args.seed)[0] if args.style == "auto" else args.style
        render_variety_sticker(st, args.text, args.out)
        print(json.dumps({"style": st, "out": args.out}, ensure_ascii=False))
    elif args.cmd == "retime-24fps":
        res = ensure_uniform_24fps(args.src, args.out, fps=args.fps)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        if res["out_mp4"] is not None and not res["was_uniform"]:
            print("已重编码为均匀时间戳", file=sys.stderr)
    elif args.cmd == "closeup-rewash":
        cap = cv2.VideoCapture(args.src)
        src_frames = []
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            src_frames.append(frame)
        cap.release()
        if not src_frames:
            raise RuntimeError(f"源镜头解码失败或为空: {args.src}")
        ref_frames = None
        if args.ref:
            cap_ref = cv2.VideoCapture(args.ref)
            ref_frames, idx = [], 0
            while True:
                ok, frame = cap_ref.read()
                if not ok:
                    break
                if idx % 24 == 0:
                    ref_frames.append(frame)
                idx += 1
            cap_ref.release()
        sec_indices = None
        if args.sec_indices:
            sec_indices = [tuple(int(v) for v in pair.split(":")) for pair in args.sec_indices.split(",") if pair]
        frames = universal_closeup_rewash(
            src_frames,
            args.n_out,
            args.shot_idx,
            ref_1fps_frames=ref_frames,
            sec_indices=sec_indices,
            target_phash=args.target_phash,
        )
        h, w = frames[0].shape[:2]
        write_h264_rawpipe(frames, args.out, width=w, height=h, fps=24, crf=args.crf)
        print(json.dumps({"out": args.out, "frames": len(frames), "shot_idx": args.shot_idx}, ensure_ascii=False))
    elif args.cmd == "verify":
        rep = verify_deliverables(args.orig, args.new, draft_dir=args.draft, phash_min_threshold=args.phash_min)
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        if not rep["passed"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
