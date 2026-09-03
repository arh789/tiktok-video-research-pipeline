from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

PROJECT_ROOT = Path(
    os.environ.get("TIKTOK_RESEARCH_ROOT", Path(__file__).resolve().parent)
).expanduser().resolve()
OUTPUT_DIR = PROJECT_ROOT / "outputs"
DATA_DIR = PROJECT_ROOT / "data"
VIDEO_DIR = DATA_DIR / "videos"
EVIDENCE_DIR = DATA_DIR / "evidence"
CHROME_PROFILE_DIR = PROJECT_ROOT / ".chrome_profile"
EDGE_PROFILE_DIR = PROJECT_ROOT / ".edge_profile"
CREDENTIALS_FILE = PROJECT_ROOT / ".tiktok_credentials.json"
EDGE_CDP_PORT = 9222
ANALYSIS_PYTHON = Path(
    os.environ.get("TIKTOK_ANALYSIS_PYTHON", sys.executable)
).expanduser()
WHISPER_MODEL = os.environ.get("TIKTOK_WHISPER_MODEL", "large-v3")
WHISPER_DEVICE = os.environ.get("TIKTOK_WHISPER_DEVICE", "cuda")
WHISPER_COMPUTE_TYPE = os.environ.get(
    "TIKTOK_WHISPER_COMPUTE_TYPE", "float16"
)
LOCAL_VISION_MODEL = os.environ.get(
    "TIKTOK_VISION_MODEL", "Qwen/Qwen2.5-VL-7B-Instruct"
)
_cuda_dll_dir = os.environ.get("TIKTOK_CUDA_DLL_DIR", "").strip()
CUDA_DLL_DIR = Path(_cuda_dll_dir).expanduser() if _cuda_dll_dir else None
VIDEO_URL_RE = re.compile(
    r"https?://(?:www\.)?tiktok\.com/@(?P<creator>[^/?#]+)/video/(?P<video_id>\d+)",
    re.IGNORECASE,
)
HASHTAG_RE = re.compile(r"(?<!\w)#([\w.]+)", re.UNICODE)
COUNT_RE = re.compile(r"(?<![\w.])(\d+(?:[.,]\d+)?)\s*([KMB])?(?!\w)", re.IGNORECASE)
SESSION_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_tt"}
GENERIC_ASR_PHRASES = {
    "thank you",
    "thank you for watching",
    "thanks for watching",
}

EXTRACT_VIDEO_CARDS_JS = r"""
() => {
  const anchors = Array.from(document.querySelectorAll('a[href*="/video/"]'));
  const seen = new Set();
  const rows = [];
  for (const anchor of anchors) {
    const match = (anchor.href || '').match(
      /https?:\/\/(?:www\.)?tiktok\.com\/@[^/?#]+\/video\/\d+/i
    );
    if (!match || seen.has(match[0])) continue;
    seen.add(match[0]);

    let node = anchor.parentElement;
    let card = anchor;
    let cardText = (anchor.innerText || '').trim();
    for (let depth = 0; depth < 12 && node; depth += 1, node = node.parentElement) {
      const videoLinks = Array.from(node.querySelectorAll('a[href*="/video/"]'));
      const distinctVideoUrls = new Set(videoLinks.map((item) =>
        ((item.href || '').match(/https?:\/\/(?:www\.)?tiktok\.com\/@[^/?#]+\/video\/\d+/i) || [])[0]
      ).filter(Boolean));
      if (distinctVideoUrls.size > 1) break;
      const text = (node.innerText || '').trim();
      if (distinctVideoUrls.size === 1 && text.length >= cardText.length && text.length <= 1800) {
        card = node;
        cardText = text;
      }
    }

    const textFrom = (selectors) => {
      for (const selector of selectors) {
        const element = card.querySelector ? card.querySelector(selector) : null;
        const text = element ? (element.innerText || element.textContent || '').trim() : '';
        if (text) return text;
      }
      return '';
    };

    rows.push({
      url: match[0],
      search_caption: textFrom([
        '[data-e2e="search-card-desc"]',
        '[data-e2e*="card-desc"]',
        '[data-e2e="video-desc"]'
      ]),
      displayed_views: textFrom([
        '[data-e2e="video-views"]',
        '[data-e2e*="video-views"]',
        '[data-e2e*="views"]'
      ]),
      search_card_text: cardText
    });
  }
  return rows;
}
"""

class EmbeddedScriptParser(HTMLParser):
    def __init__(self, target_id: str) -> None:
        super().__init__(convert_charrefs=False)
        self.target_id = target_id
        self.collecting = False
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.casefold() == "script" and dict(attrs).get("id") == self.target_id:
            self.collecting = True

    def handle_data(self, data: str) -> None:
        if self.collecting:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "script" and self.collecting:
            self.collecting = False


def embedded_script_text(html: str, script_id: str) -> str:
    parser = EmbeddedScriptParser(script_id)
    parser.feed(html)
    return "".join(parser.parts)


def number_or_none(value: Any) -> int | float | None:
    if value is None or value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(parsed):
        return None
    return int(parsed) if parsed.is_integer() else parsed


def parse_video_detail_html(html: str, video_id: str) -> dict[str, Any] | None:
    item: dict[str, Any] | None = None
    universal_text = embedded_script_text(html, "__UNIVERSAL_DATA_FOR_REHYDRATION__")
    if universal_text:
        try:
            payload = json.loads(universal_text)
            detail = payload.get("__DEFAULT_SCOPE__", {}).get("webapp.video-detail", {})
            item = detail.get("itemInfo", {}).get("itemStruct")
        except (AttributeError, json.JSONDecodeError):
            item = None
    if not item:
        sigi_text = embedded_script_text(html, "SIGI_STATE")
        if sigi_text:
            try:
                payload = json.loads(sigi_text)
                item = payload.get("ItemModule", {}).get(video_id)
            except (AttributeError, json.JSONDecodeError):
                item = None
    if not item:
        return None
    stats = {**(item.get("stats") or {}), **(item.get("statsV2") or {})}
    video = item.get("video") or {}
    music = item.get("music") or {}
    return {
        "detail_description": item.get("desc") or "",
        "create_time_unix": number_or_none(item.get("createTime")),
        "play_count": number_or_none(stats.get("playCount")),
        "like_count": number_or_none(stats.get("diggCount")),
        "comment_count": number_or_none(stats.get("commentCount")),
        "share_count": number_or_none(stats.get("shareCount")),
        "collect_count": number_or_none(stats.get("collectCount")),
        "detail_duration_seconds": number_or_none(video.get("duration")),
        "detail_width": number_or_none(video.get("width")),
        "detail_height": number_or_none(video.get("height")),
        "detail_format": video.get("format") or "",
        "music_title": music.get("title") or "",
        "music_author": music.get("authorName") or "",
    }


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load_credentials(path: Path) -> dict[str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read TikTok credentials file: {path}") from exc
    username = str(payload.get("username", "")).strip()
    password = str(payload.get("password", ""))
    if not username or not password:
        raise RuntimeError(f"TikTok credentials file is missing username or password: {path}")
    return {"username": username, "password": password}


def canonical_video_url(url: str) -> tuple[str, str, str] | None:
    match = VIDEO_URL_RE.search(url or "")
    if not match:
        return None
    creator = match.group("creator")
    video_id = match.group("video_id")
    return f"https://www.tiktok.com/@{creator}/video/{video_id}", video_id, creator


def parse_compact_count(value: str) -> int | None:
    match = COUNT_RE.search((value or "").replace(",", ""))
    if not match:
        return None
    multiplier = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(
        (match.group(2) or "").upper(), 1
    )
    return round(float(match.group(1)) * multiplier)


def fetch_oembed(video_url: str) -> dict[str, Any]:
    endpoint = "https://www.tiktok.com/oembed?" + urlencode({"url": video_url})
    request = Request(
        endpoint,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
            ),
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return {
            "oembed_status": "ok",
            "caption": payload.get("title", ""),
            "author_name": payload.get("author_name", ""),
            "author_url": payload.get("author_url", ""),
            "thumbnail_url": payload.get("thumbnail_url", ""),
            "thumbnail_width": payload.get("thumbnail_width"),
            "thumbnail_height": payload.get("thumbnail_height"),
        }
    except HTTPError as exc:
        return {"oembed_status": f"http_{exc.code}"}
    except (URLError, TimeoutError, json.JSONDecodeError) as exc:
        return {"oembed_status": f"error:{type(exc).__name__}"}


def write_netscape_cookie_file(cookies: list[dict[str, Any]]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".cookies.txt",
        prefix="tiktok_",
        dir=DATA_DIR,
        delete=False,
    )
    path = Path(handle.name)
    try:
        handle.write("# Netscape HTTP Cookie File\n")
        for cookie in cookies:
            domain = str(cookie.get("domain", ""))
            if not domain:
                continue
            include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
            secure = "TRUE" if cookie.get("secure") else "FALSE"
            expires = cookie.get("expires", 0)
            expires = int(expires) if isinstance(expires, (int, float)) and expires > 0 else 0
            name = str(cookie.get("name", "")).replace("\t", "")
            value = str(cookie.get("value", "")).replace("\t", "").replace("\n", "")
            cookie_path = str(cookie.get("path", "/"))
            handle.write(
                "\t".join(
                    (domain, include_subdomains, cookie_path, secure, str(expires), name, value)
                )
                + "\n"
            )
    finally:
        handle.close()
    return path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_tiktok_video(
    video_url: str,
    video_id: str,
    video_dir: Path,
    cookie_file: Path,
    user_agent: str,
) -> dict[str, Any]:
    from yt_dlp import YoutubeDL

    video_dir.mkdir(parents=True, exist_ok=True)
    output_template = str(video_dir / f"{video_id}.%(ext)s")
    options = {
        "cookiefile": str(cookie_file),
        "format": "best[ext=mp4][acodec!=none]/best[acodec!=none]/best",
        "http_headers": {"Referer": video_url, "User-Agent": user_agent},
        "noplaylist": True,
        "outtmpl": output_template,
        "overwrites": False,
        "quiet": True,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
        "windowsfilenames": True,
    }
    with YoutubeDL(options) as downloader:
        info = downloader.extract_info(video_url, download=True)
        requested = info.get("requested_downloads") or []
        candidate = Path(requested[0]["filepath"]) if requested else Path(downloader.prepare_filename(info))
    if not candidate.exists():
        matches = sorted(video_dir.glob(f"{video_id}.*"))
        candidate = next((path for path in matches if path.is_file()), candidate)
    if not candidate.exists() or candidate.stat().st_size == 0:
        raise RuntimeError(f"Downloaded media file was not created for {video_url}")
    return {
        "acquisition_status": "ok",
        "media_path": str(candidate),
        "file_size_bytes": candidate.stat().st_size,
        "sha256": sha256_file(candidate),
        "duration_seconds": info.get("duration"),
        "width": info.get("width"),
        "height": info.get("height"),
        "fps": info.get("fps"),
        "vcodec": info.get("vcodec"),
        "acodec": info.get("acodec"),
        "format_id": info.get("format_id"),
        "media_ext": candidate.suffix.lstrip("."),
    }


def extract_contact_sheet(media_path: Path, video_id: str) -> dict[str, Any]:
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw

    capture = cv2.VideoCapture(str(media_path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV could not open {media_path}")
    fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
    frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    duration = frame_count / fps if fps > 0 and frame_count > 0 else 0.0
    upper = max(0.0, duration - 0.05)
    timestamps = [0.0, 0.5, 1.0, 1.5, 2.0]
    if duration > 2.1:
        timestamps.extend(duration * index / 7 for index in range(1, 8))
    timestamps = sorted({round(min(max(value, 0.0), upper), 3) for value in timestamps})

    images: list[Image.Image] = []
    grays: list[Any] = []
    sampled_times: list[float] = []
    luminance_values: list[float] = []
    for timestamp in timestamps:
        capture.set(cv2.CAP_PROP_POS_MSEC, timestamp * 1000)
        ok, frame = capture.read()
        if not ok:
            continue
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(rgb)
        tile_width = 320
        tile_height = max(1, round(pil_image.height * tile_width / pil_image.width))
        pil_image = pil_image.resize((tile_width, tile_height), Image.Resampling.LANCZOS)
        tile = Image.new("RGB", (tile_width, tile_height + 26), "black")
        tile.paste(pil_image, (0, 0))
        ImageDraw.Draw(tile).text((8, tile_height + 6), f"{timestamp:.2f}s", fill="white")
        images.append(tile)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (160, 284 if height >= width else 90))
        grays.append(gray)
        luminance_values.append(float(gray.mean()))
        sampled_times.append(timestamp)
    capture.release()
    if not images:
        raise RuntimeError(f"No frames could be sampled from {media_path}")

    columns = 3
    rows = math.ceil(len(images) / columns)
    cell_width = max(image.width for image in images)
    cell_height = max(image.height for image in images)
    sheet = Image.new("RGB", (cell_width * columns, cell_height * rows), "#111111")
    for index, image in enumerate(images):
        sheet.paste(image, ((index % columns) * cell_width, (index // columns) * cell_height))
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    contact_sheet = EVIDENCE_DIR / f"{video_id}_contact_sheet.jpg"
    sheet.save(contact_sheet, quality=90)

    motion_scores = [
        float(np.mean(cv2.absdiff(previous, current)))
        for previous, current in zip(grays, grays[1:])
    ]
    return {
        "contact_sheet_path": str(contact_sheet),
        "sampled_frame_timestamps": sampled_times,
        "decoded_duration_seconds": round(duration, 3),
        "decoded_width": width,
        "decoded_height": height,
        "decoded_fps": round(fps, 3) if fps else None,
        "decoded_frame_count": frame_count,
        "mean_sample_luminance": round(sum(luminance_values) / len(luminance_values), 2),
        "mean_sample_motion": round(sum(motion_scores) / len(motion_scores), 2)
        if motion_scores
        else 0.0,
        "high_change_sample_transitions": sum(score >= 22 for score in motion_scores),
    }


def transcribe_manifest(manifest_path: Path, output_path: Path) -> None:
    import av
    from faster_whisper import WhisperModel

    items = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = WhisperModel(
        WHISPER_MODEL,
        device=WHISPER_DEVICE,
        compute_type=WHISPER_COMPUTE_TYPE,
        local_files_only=True,
    )
    with output_path.open("w", encoding="utf-8") as output:
        for index, item in enumerate(items, start=1):
            record: dict[str, Any] = {"video_id": item["video_id"]}
            if item.get("extract_visual_evidence", True):
                try:
                    record["technical_metadata"] = extract_contact_sheet(
                        Path(item["media_path"]), item["video_id"]
                    )
                except Exception as exc:
                    record["technical_metadata"] = {
                        "evidence_status": f"error:{type(exc).__name__}",
                        "evidence_error": str(exc),
                    }
            else:
                record["technical_metadata"] = {
                    "evidence_status": "not_run_transcript_only",
                }
            try:
                with av.open(item["media_path"]) as media_container:
                    has_audio = bool(media_container.streams.audio)
                    decoded_duration = (
                        float(media_container.duration / av.time_base)
                        if media_container.duration
                        else None
                    )
                    video_stream = (
                        media_container.streams.video[0]
                        if media_container.streams.video
                        else None
                    )
                    record["technical_metadata"].update(
                        {
                            "decoded_duration_seconds": round(decoded_duration, 3)
                            if decoded_duration is not None
                            else None,
                            "decoded_width": video_stream.width if video_stream else None,
                            "decoded_height": video_stream.height if video_stream else None,
                            "decoded_fps": round(float(video_stream.average_rate), 3)
                            if video_stream and video_stream.average_rate
                            else None,
                            "audio_stream_present": has_audio,
                        }
                    )
                if not has_audio:
                    record.update(
                        {
                            "transcription_status": "no_audio",
                            "transcript": "",
                            "transcript_segments": [],
                        }
                    )
                else:
                    segments, info = model.transcribe(
                        item["media_path"],
                        beam_size=5,
                        condition_on_previous_text=False,
                        vad_filter=True,
                    )
                    segment_rows = [
                        {
                            "start": round(float(segment.start), 3),
                            "end": round(float(segment.end), 3),
                            "text": segment.text.strip(),
                        }
                        for segment in segments
                        if segment.text.strip()
                    ]
                    if decoded_duration is not None:
                        filtered_rows = []
                        for row in segment_rows:
                            normalized = row["text"].casefold().strip(" .,!?")
                            if (
                                normalized in GENERIC_ASR_PHRASES
                                and row["end"] > decoded_duration + 0.1
                            ):
                                continue
                            if row["start"] >= decoded_duration + 0.1:
                                continue
                            row["end"] = min(row["end"], round(decoded_duration, 3))
                            filtered_rows.append(row)
                        segment_rows = filtered_rows
                    record.update(
                        {
                            "transcription_status": "ok",
                            "language": info.language,
                            "language_probability": round(float(info.language_probability), 4),
                            "transcript": " ".join(row["text"] for row in segment_rows),
                            "transcript_segments": segment_rows,
                        }
                    )
            except Exception as exc:
                record.update(
                    {
                        "transcription_status": f"error:{type(exc).__name__}",
                        "transcription_error": str(exc),
                        "transcript": "",
                        "transcript_segments": [],
                    }
                )
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            print(f"Transcribed {index}/{len(items)}: {item['video_id']}", flush=True)


def run_transcription_batch(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="transcription_manifest_",
        dir=DATA_DIR,
        delete=False,
    )
    manifest_path = Path(manifest_handle.name)
    output_path = manifest_path.with_suffix(".jsonl")
    try:
        json.dump(items, manifest_handle)
        manifest_handle.close()
        helper_environment = os.environ.copy()
        if CUDA_DLL_DIR is not None:
            helper_environment["PATH"] = (
                str(CUDA_DLL_DIR)
                + os.pathsep
                + helper_environment.get("PATH", "")
            )
        subprocess.run(
            [
                str(ANALYSIS_PYTHON),
                str(Path(__file__).resolve()),
                "--transcribe-manifest",
                str(manifest_path),
                "--transcript-output",
                str(output_path),
            ],
            check=True,
            env=helper_environment,
        )
        return {
            record["video_id"]: record
            for record in (
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        }
    finally:
        if not manifest_handle.closed:
            manifest_handle.close()
        manifest_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


def parse_generated_json(text: str) -> dict[str, Any]:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate)
    try:
        payload = json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start < 0 or end <= start:
            raise
        payload = json.loads(candidate[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("Local vision model did not return a JSON object.")
    return payload


def analyze_vision_manifest(manifest_path: Path, output_path: Path) -> None:
    import torch
    from PIL import Image
    from transformers import (
        AutoProcessor,
        Qwen2_5_VLForConditionalGeneration,
        logging as transformers_logging,
    )

    transformers_logging.disable_progress_bar()
    items = json.loads(manifest_path.read_text(encoding="utf-8"))
    model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
        LOCAL_VISION_MODEL,
        torch_dtype=torch.bfloat16,
        device_map="cuda",
        local_files_only=True,
    )
    processor = AutoProcessor.from_pretrained(LOCAL_VISION_MODEL, local_files_only=True)
    visual_keys = {
        "visual_premise",
        "on_screen_text_sequence",
        "shot_and_motion_grammar",
        "distinctive_features",
        "timestamped_evidence",
        "uncertainties",
    }
    fusion_keys = {
        "hook_0_to_2s",
        "spoken_premise",
        "audio_role",
        "hook_mechanism",
        "narrative_or_loop_structure",
        "affective_register",
        "format_archetype",
        "viewer_problem_or_desire_addressed",
        "call_to_action",
        "cta_type",
        "distinctive_features",
        "uncertainties",
        "analysis_confidence",
    }

    def generate_json(prompt: str, image=None, max_new_tokens: int = 800) -> dict[str, Any]:
        content: list[dict[str, Any]] = []
        if image is not None:
            content.append({"type": "image", "image": image})
        content.append({"type": "text", "text": prompt})
        messages = [{"role": "user", "content": content}]
        chat_text = processor.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        if image is not None:
            inputs = processor(
                text=[chat_text],
                images=[image],
                padding=True,
                return_tensors="pt",
            ).to("cuda")
        else:
            inputs = processor(
                text=[chat_text],
                padding=True,
                return_tensors="pt",
            ).to("cuda")
        with torch.inference_mode():
            generated = model.generate(
                **inputs,
                max_new_tokens=max_new_tokens,
                do_sample=False,
            )
        trimmed = generated[:, inputs.input_ids.shape[1] :]
        generated_text = processor.batch_decode(trimmed, skip_special_tokens=True)[0]
        return parse_generated_json(generated_text)

    with output_path.open("w", encoding="utf-8") as output:
        for index, item in enumerate(items, start=1):
            record: dict[str, Any] = {
                "video_id": item["video_id"],
                "local_vision_model": LOCAL_VISION_MODEL,
            }
            try:
                image = Image.open(item["contact_sheet_path"]).convert("RGB")
                image.thumbnail((1100, 2200), Image.Resampling.LANCZOS)
                visual_prompt = """
Analyze only the visible content of this timestamped contact sheet. Do not use or infer any TikTok caption, hashtags, audio, creator intent, authenticity, or events not visibly shown.

Return one valid JSON object with exactly these keys:
visual_premise (string); on_screen_text_sequence (array of deduplicated text strings visibly present, in order); shot_and_motion_grammar (string, acknowledging that motion is inferred from samples); distinctive_features (array of visible features); timestamped_evidence (array of objects with numeric timestamp and evidence); uncertainties (array of genuine visual ambiguities).

Rules:
- On-screen text must be visibly present in the image. Never invent hashtags.
- A text statement describing an object does not prove that object is visible.
- Do not call sampled background variation a loop unless the beginning and ending visibly match.
- Use the printed timestamp labels. Use numeric seconds without an "s" suffix.
- Describe people and events conservatively; do not call something a ghost, death, distress or paranormal unless that is visibly demonstrable.
""".strip()
                visual_analysis = generate_json(visual_prompt, image=image, max_new_tokens=800)
                missing_visual = sorted(visual_keys - set(visual_analysis))
                if missing_visual:
                    raise ValueError(
                        f"Local visual JSON omitted keys: {', '.join(missing_visual)}"
                    )

                fusion_prompt = f"""
Create a creative-strategy analysis by combining the grounded visual observations, caption metadata and speech transcript below.

GROUNDED VISUAL OBSERVATIONS:
{json.dumps(visual_analysis, ensure_ascii=False)}

CAPTION METADATA (not on-screen text unless the visual observations independently say so):
{item.get('caption', '')}

SPEECH/ASR TRANSCRIPT:
{item.get('transcript', '')}
TRANSCRIPTION STATUS: {item.get('transcription_status', '')}
TRANSCRIPTION QUALITY: {item.get('transcription_quality', '')}

Return one valid JSON object with exactly these keys:
hook_0_to_2s (string, maximum 25 words); spoken_premise (brief string); audio_role (one of: narration, dialogue, song_or_music, ambient_or_effects, no_audio, uncertain); hook_mechanism (one of: direct_question, disturbing_claim, immediate_visual_anomaly, danger_or_close_call, curiosity_gap, list_or_compilation_title, familiar_then_uncanny, source_or_livestream_claim, other); narrative_or_loop_structure (string); affective_register (short string); format_archetype (one of: text_riddle_or_fact, paranormal_evidence_single_clip, compilation_or_listicle, narrated_explainer_or_commentary, narrated_micro_story, livestream_or_source_excerpt, uncanny_visual_loop, staged_skit_or_jump_scare, text_slide_true_crime_or_history, other); viewer_problem_or_desire_addressed (string); call_to_action (string); cta_type (one of: none, explicit_follow, explicit_comment, implicit_question, unresolved_mystery, source_redirect, other); distinctive_features (array of strings); uncertainties (array of strings); analysis_confidence (number from 0 to 1).

Rules:
- Do not invent a like/share/comment CTA. If no CTA is evidenced, use "No explicit call to action" and cta_type "none".
- Treat a direct question or deliberately withheld answer as an implicit engagement device.
- If the transcript is only a generic phrase such as "Thank you", treat it as unreliable ASR, not the premise.
- If the transcript is recognizably song lyrics, set audio_role to song_or_music and do not use the lyrics as the spoken premise.
- The hook must represent only the first two seconds and must be concise.
- Add a real uncertainty whenever sampling prevents certainty about motion, editing or the ending.
""".strip()
                fusion_analysis = generate_json(fusion_prompt, max_new_tokens=850)
                missing_fusion = sorted(fusion_keys - set(fusion_analysis))
                if missing_fusion:
                    raise ValueError(
                        f"Local fusion JSON omitted keys: {', '.join(missing_fusion)}"
                    )
                analysis = {**visual_analysis, **fusion_analysis}
                analysis["distinctive_features"] = list(
                    dict.fromkeys(
                        str(value)
                        for value in [
                            *as_list(visual_analysis.get("distinctive_features")),
                            *as_list(fusion_analysis.get("distinctive_features")),
                        ]
                    )
                )
                analysis["uncertainties"] = list(
                    dict.fromkeys(
                        str(value)
                        for value in [
                            *as_list(visual_analysis.get("uncertainties")),
                            *as_list(fusion_analysis.get("uncertainties")),
                            "Motion, edit timing and the ending are inferred from sampled frames rather than continuous video review.",
                        ]
                    )
                )
                record.update(
                    {
                        "local_vision_status": "ok",
                        "analysis": analysis,
                        "visual_grounding": visual_analysis,
                        "semantic_fusion": fusion_analysis,
                    }
                )
            except Exception as exc:
                record.update(
                    {
                        "local_vision_status": f"error:{type(exc).__name__}",
                        "local_vision_error": str(exc),
                    }
                )
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
            output.flush()
            print(
                f"Local vision {index}/{len(items)}: {item['video_id']} "
                f"({record['local_vision_status']})",
                flush=True,
            )


def run_local_vision_batch(items: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    manifest_handle = tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".json",
        prefix="vision_manifest_",
        dir=DATA_DIR,
        delete=False,
    )
    manifest_path = Path(manifest_handle.name)
    output_path = manifest_path.with_suffix(".jsonl")
    try:
        json.dump(items, manifest_handle, ensure_ascii=False)
        manifest_handle.close()
        helper_environment = os.environ.copy()
        helper_environment.update(
            {
                "HF_HUB_OFFLINE": "1",
                "TRANSFORMERS_OFFLINE": "1",
                "HF_HUB_DISABLE_PROGRESS_BARS": "1",
                "TOKENIZERS_PARALLELISM": "false",
            }
        )
        subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--vision-manifest",
                str(manifest_path),
                "--vision-output",
                str(output_path),
            ],
            check=True,
            env=helper_environment,
        )
        return {
            record["video_id"]: record
            for record in (
                json.loads(line)
                for line in output_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
        }
    finally:
        if not manifest_handle.closed:
            manifest_handle.close()
        manifest_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)


async def first_visible(page, selectors: tuple[str, ...], timeout_ms: int = 20_000):
    for _ in range(max(1, timeout_ms // 500)):
        for selector in selectors:
            candidates = page.locator(selector)
            for index in range(await candidates.count()):
                candidate = candidates.nth(index)
                if await candidate.is_visible():
                    return candidate
        await page.wait_for_timeout(500)
    return None


async def has_authenticated_session(context) -> bool:
    cookies = await context.cookies("https://www.tiktok.com/")
    return any(
        cookie.get("name") in SESSION_COOKIE_NAMES and cookie.get("value")
        for cookie in cookies
    )


async def login_with_credentials(page, credentials: dict[str, str]) -> None:
    print("TikTok login is required; signing in with the external credentials file.", flush=True)
    await page.goto(
        "https://www.tiktok.com/login/phone-or-email/email",
        wait_until="domcontentloaded",
        timeout=90_000,
    )
    await page.wait_for_timeout(3_000)

    username_input = await first_visible(
        page,
        (
            'input[name="username"]',
            'input[autocomplete="username"]',
            'input[placeholder*="Email or username" i]',
            'input[type="text"]',
        ),
    )
    password_input = await first_visible(
        page,
        (
            'input[type="password"]',
            'input[name="password"]',
            'input[autocomplete="current-password"]',
        ),
    )
    if username_input is None or password_input is None:
        raise RuntimeError("TikTok email/password login fields were not found.")

    await username_input.fill(credentials["username"])
    await password_input.fill(credentials["password"])
    submit = await first_visible(
        page,
        (
            'button[data-e2e="login-button"]',
            'button[type="submit"]',
            'button:has-text("Log in")',
        ),
    )
    if submit is None:
        raise RuntimeError("TikTok login submit button was not found.")
    await submit.click()

    challenge_reported = False
    for _ in range(150):
        if await has_authenticated_session(page.context):
            print("TikTok login session detected.", flush=True)
            return
        body_text = (await page.locator("body").inner_text(timeout=20_000)).casefold()
        if not challenge_reported and any(
            marker in body_text
            for marker in ("verify", "verification code", "captcha", "security check")
        ):
            print(
                "TikTok requested an interactive verification step. "
                "Complete it in the open Chrome window; waiting up to five minutes.",
                flush=True,
            )
            challenge_reported = True
        await page.wait_for_timeout(2_000)
    raise RuntimeError("TikTok login did not complete within five minutes.")


async def wait_for_manual_login(page) -> None:
    print(
        "TikTok is not authenticated. Log in manually in the open Edge window; "
        "waiting up to ten minutes.",
        flush=True,
    )
    await page.goto("https://www.tiktok.com/login", wait_until="domcontentloaded", timeout=90_000)
    for _ in range(300):
        if await has_authenticated_session(page.context):
            print("TikTok login session detected; continuing automatically.", flush=True)
            return
        await page.wait_for_timeout(2_000)
    raise RuntimeError("TikTok manual login did not complete within ten minutes.")


async def collect_first_results(
    page,
    query: str,
    limit: int,
    credentials: dict[str, str] | None,
) -> list[dict[str, Any]]:
    search_url = f"https://www.tiktok.com/search/video?q={quote(query)}"
    await page.goto(search_url, wait_until="domcontentloaded", timeout=90_000)
    await page.wait_for_timeout(8_000)

    body_text = (await page.locator("body").inner_text(timeout=20_000)).casefold()
    if any(marker in body_text for marker in ("captcha", "verify to continue", "security check")):
        print("TikTok verification is visible; waiting 30 seconds for manual completion.")
        await page.wait_for_timeout(30_000)

    authenticated = await has_authenticated_session(page.context)
    if not authenticated:
        if credentials is not None:
            await login_with_credentials(page, credentials)
        else:
            await wait_for_manual_login(page)
        print("Reopening the authenticated search results.", flush=True)
        await page.goto(search_url, wait_until="domcontentloaded", timeout=90_000)
        await page.wait_for_timeout(8_000)

    results: dict[str, dict[str, Any]] = {}
    stagnant_rounds = 0
    previous_count = 0
    for _ in range(12):
        cards = await page.evaluate(EXTRACT_VIDEO_CARDS_JS)
        for card in cards:
            parsed = canonical_video_url(card.get("url", ""))
            if not parsed:
                continue
            video_url, video_id, creator = parsed
            if video_id not in results:
                results[video_id] = {
                    "search_term": query,
                    "search_rank": len(results) + 1,
                    "video_url": video_url,
                    "video_id": video_id,
                    "creator_handle": creator,
                    "search_caption": card.get("search_caption", ""),
                    "displayed_views": card.get("displayed_views", ""),
                    "search_card_text": card.get("search_card_text", ""),
                    "collected_at": utc_now(),
                }
                if len(results) >= limit:
                    return list(results.values())

        current_count = len(results)
        stagnant_rounds = stagnant_rounds + 1 if current_count == previous_count else 0
        if stagnant_rounds >= 4:
            break
        previous_count = current_count
        await page.mouse.wheel(0, 2200)
        await page.wait_for_timeout(1_500)
    return list(results.values())[:limit]


async def enrich_video_detail_metadata(context, rows: list[dict[str, Any]]) -> None:
    for index, row in enumerate(rows, start=1):
        try:
            response = await context.request.get(row["video_url"], timeout=90_000)
            if not response.ok:
                raise RuntimeError(f"TikTok detail request returned HTTP {response.status}.")
            detail = parse_video_detail_html(await response.text(), row["video_id"])
            if not detail:
                raise RuntimeError("TikTok embedded video detail data was not found.")
            row.update(detail)
            row["detail_metadata_status"] = "ok"
            create_time = detail.get("create_time_unix")
            row["published_at_utc"] = (
                datetime.fromtimestamp(create_time, timezone.utc).isoformat(timespec="seconds")
                if create_time
                else published_at_from_video_id(row["video_id"])
            )
        except Exception as exc:
            row["detail_metadata_status"] = f"error:{type(exc).__name__}"
            row["detail_metadata_error"] = str(exc)
            row["published_at_utc"] = published_at_from_video_id(row["video_id"])
        print(
            f"Detailed {index}/{len(rows)}: {row['video_id']} "
            f"({row['detail_metadata_status']})",
            flush=True,
        )
        await asyncio.sleep(0.75)


def edge_executable() -> Path:
    configured_path = os.environ.get("TIKTOK_EDGE_EXECUTABLE", "").strip()
    candidates = tuple([Path(configured_path).expanduser()] if configured_path else []) + (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise RuntimeError("Microsoft Edge executable was not found.")


def cdp_endpoint_available(url: str) -> bool:
    with urlopen(url, timeout=1):
        return True


def configure_isolated_edge_profile() -> None:
    default_profile = EDGE_PROFILE_DIR / "Default"
    default_profile.mkdir(parents=True, exist_ok=True)
    preferences_path = default_profile / "Preferences"
    preferences = {
        "browser": {"has_seen_welcome_page": True},
        "credentials_enable_service": False,
        "profile": {"password_manager_enabled": False},
        "signin": {"allowed": False, "allowed_on_next_startup": False},
        "sync": {"requested": False},
    }
    temporary = preferences_path.with_suffix(".tmp")
    temporary.write_text(json.dumps(preferences), encoding="utf-8")
    temporary.replace(preferences_path)


def remove_profile_entry(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def sanitize_isolated_edge_profile() -> None:
    expected = PROJECT_ROOT / ".edge_profile"
    if EDGE_PROFILE_DIR.resolve() != expected.resolve():
        raise RuntimeError(f"Refusing to sanitize unexpected Edge profile: {EDGE_PROFILE_DIR}")
    if not EDGE_PROFILE_DIR.exists():
        return

    for entry in EDGE_PROFILE_DIR.iterdir():
        if entry.name not in {"Local State", "Default"}:
            remove_profile_entry(entry)

    default_profile = EDGE_PROFILE_DIR / "Default"
    if not default_profile.exists():
        return
    retained_default = {
        "Network",
        "Preferences",
        "Local Storage",
        "IndexedDB",
    }
    for entry in default_profile.iterdir():
        if entry.name not in retained_default:
            remove_profile_entry(entry)

    indexed_db = default_profile / "IndexedDB"
    if indexed_db.exists():
        for entry in indexed_db.iterdir():
            if not entry.name.startswith("https_www.tiktok.com_"):
                remove_profile_entry(entry)

    retained_cookie_domains: list[str] = []
    network = default_profile / "Network"
    if network.exists():
        for entry in network.iterdir():
            if entry.name != "Cookies":
                remove_profile_entry(entry)
        cookie_db = network / "Cookies"
        if cookie_db.exists():
            connection = sqlite3.connect(cookie_db)
            try:
                connection.execute(
                    """
                    DELETE FROM cookies
                    WHERE host_key != 'tiktok.com'
                      AND host_key NOT LIKE '%.tiktok.com'
                      AND host_key != 'tiktokw.us'
                      AND host_key NOT LIKE '%.tiktokw.us'
                    """
                )
                connection.commit()
                retained_cookie_domains = [
                    row[0]
                    for row in connection.execute(
                        "SELECT DISTINCT host_key FROM cookies ORDER BY host_key"
                    )
                ]
                connection.execute("VACUUM")
            finally:
                connection.close()

    local_state_path = EDGE_PROFILE_DIR / "Local State"
    try:
        local_state = json.loads(local_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        local_state = {}
    safe_local_state = {}
    if isinstance(local_state.get("os_crypt"), dict):
        safe_local_state["os_crypt"] = local_state["os_crypt"]
    safe_local_state["profile"] = {
        "info_cache": {
            "Default": {
                "is_using_default_name": False,
                "name": "TikTok automation",
            }
        }
    }
    local_state_temp = local_state_path.with_suffix(".tmp")
    local_state_temp.write_text(json.dumps(safe_local_state), encoding="utf-8")
    local_state_temp.replace(local_state_path)
    configure_isolated_edge_profile()

    size = sum(path.stat().st_size for path in EDGE_PROFILE_DIR.rglob("*") if path.is_file())
    print(
        f"Sanitized isolated Edge profile: {size / (1024 * 1024):.2f} MB retained; "
        f"cookie domains: {retained_cookie_domains}.",
        flush=True,
    )


async def launch_edge_for_cdp(
    headless: bool,
) -> tuple[subprocess.Popen | None, str, bool]:
    endpoint = f"http://127.0.0.1:{EDGE_CDP_PORT}"
    version_url = f"{endpoint}/json/version"
    try:
        if await asyncio.to_thread(cdp_endpoint_available, version_url):
            print(f"Reusing the open isolated Edge session at {endpoint}.", flush=True)
            return None, endpoint, True
    except (URLError, TimeoutError, OSError):
        pass

    sanitize_isolated_edge_profile()
    configure_isolated_edge_profile()
    arguments = [
        str(edge_executable()),
        f"--user-data-dir={EDGE_PROFILE_DIR}",
        "--profile-directory=Default",
        f"--remote-debugging-port={EDGE_CDP_PORT}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-sync",
        "--disable-background-mode",
        "--mute-audio",
        "--disable-features=msEdgeAccountConsistency,msEdgeSync,msForceBrowserSignIn,msStartupBoost",
        "--disable-session-crashed-bubble",
        "--new-window",
        "about:blank",
    ]
    if headless:
        arguments.insert(1, "--headless=new")
    creation_flags = 0
    if sys.platform == "win32":
        creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    process = subprocess.Popen(arguments, creationflags=creation_flags)
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("Edge exited before its debugging endpoint became available.")
        try:
            await asyncio.to_thread(cdp_endpoint_available, version_url)
            return process, endpoint, False
        except (URLError, TimeoutError, OSError):
            await asyncio.sleep(0.25)
    process.terminate()
    raise RuntimeError(
        "Edge debugging endpoint did not start. Close every Edge window and run the collector again."
    )


def published_at_from_video_id(video_id: str) -> str | None:
    try:
        timestamp = int(video_id) >> 32
        return datetime.fromtimestamp(timestamp, timezone.utc).isoformat(timespec="seconds")
    except (ValueError, OSError, OverflowError):
        return None


def infer_format_archetype(caption: str, hashtags: list[str]) -> str:
    text = f"{caption} {' '.join(hashtags)}".casefold()
    if any(token in text for token in ("analoghorror", "dreamcore", "liminal", "weirdcore", "wierdcore")):
        return "analog-horror or uncanny-aesthetic montage"
    if any(token in text for token in ("paranormal", "ghost", "unexplained")):
        return "paranormal evidence or unexplained-encounter clip"
    if "livestream" in text or "full video" in text:
        return "excerpted livestream or source-video highlight"
    if any(token in text for token in ("story", "reddit")):
        return "short-form narrated horror story"
    return "short-form creepy reveal or horror-evidence clip"


def baseline_record(
    row: dict[str, Any],
    acquisition: dict[str, Any],
    evidence: dict[str, Any],
    transcript: dict[str, Any],
) -> dict[str, Any]:
    hashtags = json.loads(row.get("hashtags") or "[]")
    caption = row.get("caption", "")
    segments = transcript.get("transcript_segments", [])
    opening_speech = " ".join(segment["text"] for segment in segments if segment["start"] < 2).strip()
    transcript_text = transcript.get("transcript", "")
    normalized_transcript = transcript_text.casefold().strip(" .,!?")
    suspected_asr_hallucination = normalized_transcript in GENERIC_ASR_PHRASES
    caption_lower = caption.casefold()
    if "?" in caption:
        call_to_action = "Implicit comment prompt through a direct question."
    elif "full video" in caption_lower:
        call_to_action = "Watch the full source video or visit the credited creator."
    else:
        call_to_action = "No explicit call to action detected in the caption or transcript."
    motion = float(evidence.get("mean_sample_motion") or 0)
    change_count = int(evidence.get("high_change_sample_transitions") or 0)
    luminance = float(evidence.get("mean_sample_luminance") or 0)
    affect = "fear, unease, suspense and curiosity"
    distinctive = [f"#{tag}" for tag in hashtags[:5]]
    distinctive.extend(
        [
            "dark visual register" if luminance < 80 else "mid-to-bright visual register",
            "high sampled visual change" if motion >= 22 else "low-to-moderate sampled visual change",
        ]
    )
    timestamped = [
        {"start": segment["start"], "end": segment["end"], "evidence": segment["text"]}
        for segment in segments
    ]
    if not timestamped:
        timestamped = [
            {
                "timestamp": timestamp,
                "evidence": f"Representative frame included in {evidence.get('contact_sheet_path', '')}",
            }
            for timestamp in evidence.get("sampled_frame_timestamps", [])[:5]
        ]
    uncertainties = [
        "On-screen text has not yet been OCR-transcribed.",
        "Visual premise and loop structure require semantic review of the contact sheet or full video.",
    ]
    transcription_status = transcript.get("transcription_status")
    if transcription_status not in {"ok", "no_audio"}:
        uncertainties.append("Speech transcription was unavailable or failed.")
    if transcription_status == "no_audio":
        spoken_premise = "No audio stream is present in the acquired video."
    elif suspected_asr_hallucination:
        spoken_premise = "No reliable spoken premise; only a likely music/noise ASR hallucination was returned."
        uncertainties.append(
            f"Faster-Whisper returned only {transcript_text!r}; treat it as likely music/noise hallucination."
        )
    else:
        spoken_premise = transcript_text or "No intelligible speech detected by Faster-Whisper."
    return {
        "video_url": row["video_url"],
        "video_id": row["video_id"],
        "creator_handle": row["creator_handle"],
        "search_term": row["search_term"],
        "search_rank": row["search_rank"],
        "search_appearances": row.get("search_appearances") or [
            {"search_term": row["search_term"], "search_rank": row["search_rank"]}
        ],
        "published_at_utc": row.get("published_at_utc") or published_at_from_video_id(row["video_id"]),
        "caption": caption,
        "hashtags": hashtags,
        "engagement_metrics": {
            "play_count": row.get("play_count"),
            "like_count": row.get("like_count"),
            "comment_count": row.get("comment_count"),
            "share_count": row.get("share_count"),
            "collect_count": row.get("collect_count"),
            "captured_at": row.get("collected_at"),
        },
        "acquisition": acquisition,
        "technical_metadata": evidence,
        "transcription": transcript,
        "hook_0_to_2s": opening_speech
        or (f"Caption-led opening premise: {caption}" if caption else "No opening speech detected."),
        "visual_premise": "Representative visual evidence acquired; semantic description pending review.",
        "spoken_premise": spoken_premise,
        "on_screen_text_sequence": [],
        "shot_and_motion_grammar": (
            f"{change_count} high-change transitions across sampled frames; "
            f"mean sampled motion score {motion:.2f}."
        ),
        "narrative_or_loop_structure": "Pending semantic review of the full clip and ending frames.",
        "affective_register": affect,
        "format_archetype": infer_format_archetype(caption, hashtags),
        "viewer_problem_or_desire_addressed": (
            "Provides a compact dose of suspense, mystery, fear and apparently unusual evidence."
        ),
        "call_to_action": call_to_action,
        "distinctive_features": distinctive,
        "timestamped_evidence": timestamped,
        "uncertainties": uncertainties,
    }


def as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def repair_mojibake_text(value: str) -> str:
    text = value or ""
    markers = ("Ã", "â", "ðŸ", "ï¸", "ã‚")
    for _ in range(2):
        before_score = sum(text.count(marker) for marker in markers)
        if before_score == 0:
            break
        try:
            candidate = text.encode("cp1252").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            break
        after_score = sum(candidate.count(marker) for marker in markers)
        if after_score >= before_score:
            break
        text = candidate
    return text


def normalize_seconds(value: Any) -> float | None:
    if value is None:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value))
    if not match:
        return None
    try:
        return round(float(match.group(0)), 3)
    except ValueError:
        return None


def normalize_evidence_entries(
    visual_entries: list[Any],
    existing_entries: list[Any],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for entry in visual_entries:
        if not isinstance(entry, dict):
            continue
        start = normalize_seconds(
            entry.get("start_seconds", entry.get("timestamp", entry.get("start")))
        )
        if start is None:
            continue
        end = normalize_seconds(entry.get("end_seconds", entry.get("end")))
        normalized.append(
            {
                "start_seconds": start,
                "end_seconds": end if end is not None else start,
                "modality": "visual_sample",
                "evidence": str(entry.get("evidence", "")).strip(),
            }
        )
    for entry in existing_entries:
        if not isinstance(entry, dict) or "start" not in entry:
            continue
        start = normalize_seconds(entry.get("start"))
        if start is None:
            continue
        end = normalize_seconds(entry.get("end"))
        normalized.append(
            {
                "start_seconds": start,
                "end_seconds": end if end is not None else start,
                "modality": "speech",
                "evidence": str(entry.get("evidence", "")).strip(),
            }
        )
    return sorted(normalized, key=lambda entry: (entry["start_seconds"], entry["modality"]))


def prepare_existing_records(records: list[dict[str, Any]]) -> None:
    for record in records:
        record["caption"] = repair_mojibake_text(str(record.get("caption", "")))
        record["hashtags"] = [
            repair_mojibake_text(str(hashtag)) for hashtag in as_list(record.get("hashtags"))
        ]
        transcription = record.get("transcription", {})
        transcript = str(transcription.get("transcript", ""))
        normalized = transcript.casefold().strip(" .,!?")
        if transcription.get("transcription_status") == "no_audio":
            quality = "no_audio"
        elif normalized in GENERIC_ASR_PHRASES:
            quality = "suspected_hallucination"
            record["spoken_premise"] = (
                "No reliable spoken premise; only a likely music/noise ASR hallucination was returned."
            )
        elif transcription.get("transcription_status") == "ok" and transcript.strip():
            quality = "usable"
        elif transcription.get("transcription_status") == "ok":
            quality = "no_speech"
        else:
            quality = "unavailable"
        transcription["quality_status"] = quality


def apply_local_vision_results(
    records: list[dict[str, Any]],
    local_vision_results: dict[str, dict[str, Any]],
    local_vision_limit: int,
) -> None:
    semantic_keys = {
        "hook_0_to_2s",
        "spoken_premise",
        "audio_role",
        "hook_mechanism",
        "visual_premise",
        "on_screen_text_sequence",
        "shot_and_motion_grammar",
        "narrative_or_loop_structure",
        "affective_register",
        "format_archetype",
        "viewer_problem_or_desire_addressed",
        "call_to_action",
        "cta_type",
        "distinctive_features",
        "timestamped_evidence",
        "uncertainties",
        "analysis_confidence",
    }
    for index, record in enumerate(records):
        vision_result = local_vision_results.get(record["video_id"])
        if vision_result is not None:
            vision_status = vision_result.get("local_vision_status", "unknown")
        elif index >= local_vision_limit:
            vision_status = "not_run_poc_limit"
        else:
            vision_status = "not_run_no_contact_sheet"
        record["analysis_provenance"] = {
            "speech_model": WHISPER_MODEL,
            "speech_status": record.get("transcription", {}).get("transcription_status"),
            "speech_quality_status": record.get("transcription", {}).get("quality_status"),
            "visual_model": LOCAL_VISION_MODEL,
            "visual_status": vision_status,
            "visual_scope_limit": local_vision_limit,
        }
        if not vision_result or vision_status != "ok":
            continue
        vision_analysis = vision_result.get("analysis") or {}
        record["local_vision_analysis"] = vision_analysis
        record["local_visual_grounding"] = vision_result.get("visual_grounding", {})
        record["local_semantic_fusion"] = vision_result.get("semantic_fusion", {})
        for key, value in vision_analysis.items():
            if key not in semantic_keys:
                continue
            if key == "distinctive_features":
                value = list(
                    dict.fromkeys(
                        str(feature)
                        for feature in [*as_list(record.get(key)), *as_list(value)]
                    )
                )
            elif key == "uncertainties":
                retained = [
                    str(uncertainty)
                    for uncertainty in as_list(record.get(key))
                    if not str(uncertainty).startswith("On-screen text has not")
                    and not str(uncertainty).startswith("Visual premise and loop structure")
                ]
                value = list(
                    dict.fromkeys(
                        str(uncertainty)
                        for uncertainty in [*as_list(value), *retained]
                    )
                )
            elif key == "timestamped_evidence":
                value = normalize_evidence_entries(
                    as_list(value),
                    as_list(record.get(key)),
                )
            elif key == "on_screen_text_sequence":
                value = [str(text) for text in as_list(value)]
            record[key] = value


def mark_no_audio_records(records: list[dict[str, Any]]) -> None:
    try:
        import av
    except ModuleNotFoundError:
        av = None

    for record in records:
        transcription = record.get("transcription", {})
        media_path = record.get("acquisition", {}).get("media_path")
        if not media_path or not Path(media_path).exists():
            continue
        if av is not None:
            try:
                with av.open(media_path) as media_container:
                    no_audio = not bool(media_container.streams.audio)
            except Exception:
                continue
        else:
            no_audio = (
                transcription.get("transcription_status") == "error:IndexError"
                and transcription.get("transcription_error") == "tuple index out of range"
            )
        if not no_audio:
            continue
        record["transcription"] = {
            "video_id": record["video_id"],
            "transcription_status": "no_audio",
            "transcript": "",
            "transcript_segments": [],
        }
        record["spoken_premise"] = "No audio stream is present in the acquired video."
        record["uncertainties"] = [
            uncertainty
            for uncertainty in as_list(record.get("uncertainties"))
            if uncertainty != "Speech transcription was unavailable or failed."
        ]


def enrich_existing_analysis_local_vision(analysis_path: Path, local_vision_limit: int) -> None:
    records = [
        json.loads(line)
        for line in analysis_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    mark_no_audio_records(records)
    prepare_existing_records(records)
    vision_items = [
        {
            "video_id": record["video_id"],
            "contact_sheet_path": record["technical_metadata"]["contact_sheet_path"],
            "caption": record.get("caption", ""),
            "transcript": record.get("transcription", {}).get("transcript", ""),
            "transcription_status": record.get("transcription", {}).get(
                "transcription_status", ""
            ),
            "transcription_quality": record.get("transcription", {}).get(
                "quality_status", ""
            ),
        }
        for record in records[:local_vision_limit]
        if record.get("technical_metadata", {}).get("contact_sheet_path")
    ]
    local_vision_results = run_local_vision_batch(vision_items) if vision_items else {}
    apply_local_vision_results(records, local_vision_results, local_vision_limit)
    temporary = analysis_path.with_suffix(analysis_path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(analysis_path)
    print(f"Enriched {len(records)} existing baseline records at {analysis_path}", flush=True)


async def acquire_and_analyze_videos(
    context,
    page,
    rows: list[dict[str, Any]],
    video_dir: Path,
    analysis_output: Path,
    local_vision_limit: int,
) -> list[dict[str, Any]]:
    cookies = await context.cookies("https://www.tiktok.com/")
    user_agent = await page.evaluate("() => navigator.userAgent")
    cookie_file = write_netscape_cookie_file(cookies)
    acquisition_by_id: dict[str, dict[str, Any]] = {}
    try:
        for index, row in enumerate(rows, start=1):
            video_id = row["video_id"]
            try:
                acquisition = await asyncio.to_thread(
                    download_tiktok_video,
                    row["video_url"],
                    video_id,
                    video_dir,
                    cookie_file,
                    user_agent,
                )
            except Exception as exc:
                acquisition = {
                    "acquisition_status": f"error:{type(exc).__name__}",
                    "acquisition_error": str(exc),
                }
            acquisition_by_id[video_id] = acquisition
            print(
                f"Acquired {index}/{len(rows)}: {video_id} "
                f"({acquisition['acquisition_status']})",
                flush=True,
            )
            await asyncio.sleep(1)
    finally:
        cookie_file.unlink(missing_ok=True)

    transcription_items = [
        {
            "video_id": video_id,
            "media_path": acquisition["media_path"],
            "extract_visual_evidence": local_vision_limit > 0,
        }
        for video_id, acquisition in acquisition_by_id.items()
        if acquisition.get("acquisition_status") == "ok"
    ]
    media_analysis = (
        await asyncio.to_thread(run_transcription_batch, transcription_items)
        if transcription_items
        else {}
    )
    records = [
        baseline_record(
            row,
            acquisition_by_id[row["video_id"]],
            media_analysis.get(row["video_id"], {}).get("technical_metadata", {}),
            {
                key: value
                for key, value in media_analysis.get(
                    row["video_id"],
                    {
                        "transcription_status": "not_run",
                        "transcript": "",
                        "transcript_segments": [],
                    },
                ).items()
                if key != "technical_metadata"
            },
        )
        for row in rows
    ]
    prepare_existing_records(records)
    vision_items = [
        {
            "video_id": record["video_id"],
            "contact_sheet_path": record["technical_metadata"]["contact_sheet_path"],
            "caption": record["caption"],
            "transcript": record["transcription"].get("transcript", ""),
            "transcription_status": record["transcription"].get("transcription_status", ""),
            "transcription_quality": record["transcription"].get("quality_status", ""),
        }
        for record in records[:local_vision_limit]
        if record.get("technical_metadata", {}).get("contact_sheet_path")
    ]
    local_vision_results = (
        await asyncio.to_thread(run_local_vision_batch, vision_items)
        if vision_items
        else {}
    )
    apply_local_vision_results(records, local_vision_results, local_vision_limit)
    analysis_output.parent.mkdir(parents=True, exist_ok=True)
    temporary = analysis_output.with_suffix(analysis_output.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        for record in records:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    temporary.replace(analysis_output)
    print(f"Wrote {len(records)} baseline records to {analysis_output}", flush=True)
    return records


async def run(
    query: str,
    related_queries: list[str],
    limit: int,
    output_path: Path,
    credentials_path: Path,
    browser_name: str,
    auto_login: bool,
    headless: bool,
    close_browser: bool,
    analyze_videos: bool,
    video_dir: Path,
    analysis_output: Path,
    local_vision_limit: int,
) -> None:
    from playwright.async_api import async_playwright

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    profile_dir = EDGE_PROFILE_DIR if browser_name == "edge" else CHROME_PROFILE_DIR
    profile_dir.mkdir(parents=True, exist_ok=True)
    credentials = load_credentials(credentials_path) if auto_login else None
    playwright = await async_playwright().start()
    browser = None
    context = None
    edge_process = None
    reused_edge = False
    try:
        if browser_name == "edge":
            edge_process, endpoint, reused_edge = await launch_edge_for_cdp(headless)
            browser = await playwright.chromium.connect_over_cdp(endpoint)
            context = browser.contexts[0]
        else:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=headless,
                viewport=None,
                locale="en-AU",
                args=["--start-maximized"],
            )
        page = context.pages[0] if context.pages else await context.new_page()
        rows_by_id: dict[str, dict[str, Any]] = {}
        for search_query in [query, *related_queries]:
            candidates = await collect_first_results(page, search_query, limit, credentials)
            for candidate in candidates:
                appearance = {
                    "search_term": candidate["search_term"],
                    "search_rank": candidate["search_rank"],
                }
                existing = rows_by_id.get(candidate["video_id"])
                if existing is None:
                    candidate["search_appearances"] = [appearance]
                    rows_by_id[candidate["video_id"]] = candidate
                elif appearance not in existing["search_appearances"]:
                    existing["search_appearances"].append(appearance)
            print(
                f"Collected {len(candidates)} results for {search_query!r}; "
                f"{len(rows_by_id)} unique videos so far.",
                flush=True,
            )
            if len(rows_by_id) >= limit:
                break
        rows = list(rows_by_id.values())[:limit]
        if len(rows) < limit:
            body_preview = (await page.locator("body").inner_text(timeout=20_000))[:2500]
            video_anchor_count = await page.locator('a[href*="/video/"]').count()
            print(f"Current URL: {page.url}")
            print(f"Page title: {await page.title()}")
            print(f"Visible video-link anchors: {video_anchor_count}")
            print(f"Page text preview: {body_preview!r}")
            raise RuntimeError(f"TikTok returned only {len(rows)} distinct video results; expected {limit}.")

        for index, row in enumerate(rows, start=1):
            metadata = await asyncio.to_thread(fetch_oembed, row["video_url"])
            row.update(metadata)
            row["caption"] = metadata.get("caption") or row["search_caption"]
            row["author_name"] = metadata.get("author_name") or row["creator_handle"]
            row["hashtags"] = json.dumps(
                sorted(set(HASHTAG_RE.findall(row["caption"])), key=str.casefold),
                ensure_ascii=False,
            )
            row["displayed_view_count"] = parse_compact_count(row["displayed_views"])
            print(f"Enriched {index}/{len(rows)}: {row['video_url']}")

        await enrich_video_detail_metadata(context, rows)
        await page.bring_to_front()

        fields = [
            "search_term",
            "search_rank",
            "search_appearances",
            "video_url",
            "video_id",
            "creator_handle",
            "author_name",
            "author_url",
            "caption",
            "hashtags",
            "displayed_views",
            "displayed_view_count",
            "play_count",
            "like_count",
            "comment_count",
            "share_count",
            "collect_count",
            "published_at_utc",
            "create_time_unix",
            "detail_duration_seconds",
            "detail_width",
            "detail_height",
            "detail_format",
            "music_title",
            "music_author",
            "detail_metadata_status",
            "detail_metadata_error",
            "detail_description",
            "thumbnail_url",
            "thumbnail_width",
            "thumbnail_height",
            "oembed_status",
            "search_caption",
            "search_card_text",
            "collected_at",
        ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_suffix(output_path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(
                {
                    **row,
                    "search_appearances": json.dumps(
                        row.get("search_appearances") or [], ensure_ascii=False
                    ),
                }
                for row in rows
            )
        temporary.replace(output_path)
        print(f"Wrote {len(rows)} rows to {output_path}")
        if analyze_videos:
            await acquire_and_analyze_videos(
                context,
                page,
                rows,
                video_dir,
                analysis_output,
                local_vision_limit,
            )
    finally:
        if browser is not None:
            if close_browser:
                try:
                    pages = context.pages if context is not None else []
                    if pages:
                        cdp_session = await context.new_cdp_session(pages[0])
                        await cdp_session.send("Browser.close")
                    else:
                        await browser.close()
                except Exception:
                    await browser.close()
            else:
                print(
                    f"Leaving the isolated Edge session open for reuse and troubleshooting at "
                    f"http://127.0.0.1:{EDGE_CDP_PORT}.",
                    flush=True,
                )
        elif context is not None:
            await context.close()
        await playwright.stop()
        if close_browser and edge_process is not None:
            try:
                await asyncio.to_thread(edge_process.wait, 10)
            except subprocess.TimeoutExpired:
                edge_process.terminate()
                await asyncio.to_thread(edge_process.wait, 10)
        if close_browser and browser_name == "edge":
            sanitize_isolated_edge_profile()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect the first TikTok video results and public metadata.")
    parser.add_argument("query", nargs="?", default="creepy tok")
    parser.add_argument(
        "--related-query",
        action="append",
        default=[],
        help="Additional closely related search term; repeat until the requested unique-video limit is reachable.",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_DIR / "creepy_tok_first_10_videos.csv",
    )
    parser.add_argument("--credentials", type=Path, default=CREDENTIALS_FILE)
    parser.add_argument("--browser", choices=("edge", "chrome"), default="edge")
    parser.add_argument(
        "--auto-login",
        action="store_true",
        help="Opt in to password submission from the credentials file. Manual session reuse is the default.",
    )
    parser.add_argument("--headless", action="store_true")
    parser.add_argument(
        "--close-browser",
        action="store_true",
        help="Close and sanitize the isolated Edge session after collection. It stays open by default.",
    )
    parser.add_argument(
        "--analyze-videos",
        action="store_true",
        help="Download the collected videos, extract evidence, transcribe audio and write baseline JSONL.",
    )
    parser.add_argument("--video-dir", type=Path, default=VIDEO_DIR)
    parser.add_argument(
        "--analysis-output",
        type=Path,
        default=OUTPUT_DIR / "creepy_tok_baseline_analysis.jsonl",
    )
    parser.add_argument(
        "--local-vision-limit",
        type=int,
        default=0,
        help="Opt in to the legacy local Qwen2.5-VL pass for the first N videos; 0 disables it (default).",
    )
    parser.add_argument(
        "--enrich-existing-analysis",
        action="store_true",
        help="Apply the bounded local vision/no-audio pass to an existing --analysis-output without recollecting TikTok data.",
    )
    parser.add_argument("--transcribe-manifest", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--transcript-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--vision-manifest", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--vision-output", type=Path, help=argparse.SUPPRESS)
    parser.add_argument(
        "--sanitize-profile-only",
        action="store_true",
        help="Remove non-TikTok data from the isolated Edge profile without launching a browser.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    arguments = parse_args()
    if arguments.transcribe_manifest:
        if arguments.transcript_output is None:
            raise SystemExit("--transcript-output is required with --transcribe-manifest")
        transcribe_manifest(arguments.transcribe_manifest, arguments.transcript_output)
        raise SystemExit(0)
    if arguments.vision_manifest:
        if arguments.vision_output is None:
            raise SystemExit("--vision-output is required with --vision-manifest")
        analyze_vision_manifest(arguments.vision_manifest, arguments.vision_output)
        raise SystemExit(0)
    if arguments.sanitize_profile_only:
        sanitize_isolated_edge_profile()
        raise SystemExit(0)
    if arguments.limit < 1:
        raise SystemExit("--limit must be at least 1")
    if arguments.local_vision_limit < 0:
        raise SystemExit("--local-vision-limit cannot be negative")
    if arguments.enrich_existing_analysis:
        enrich_existing_analysis_local_vision(
            arguments.analysis_output,
            arguments.local_vision_limit,
        )
        raise SystemExit(0)
    asyncio.run(
        run(
            arguments.query,
            arguments.related_query,
            arguments.limit,
            arguments.output,
            arguments.credentials,
            arguments.browser,
            arguments.auto_login,
            arguments.headless,
            arguments.close_browser,
            arguments.analyze_videos,
            arguments.video_dir,
            arguments.analysis_output,
            arguments.local_vision_limit,
        )
    )
