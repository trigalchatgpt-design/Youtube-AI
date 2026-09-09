from __future__ import annotations

import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

SHOT_MAX_SECONDS = 4.7
VOICE_SPEED = 1.12
VIDEO_FPS = 8
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def _font(size: int, bold: bool = True):
    path = FONT_BOLD if bold else FONT_REGULAR
    if Path(path).exists():
        return ImageFont.truetype(path, size=size)
    return ImageFont.load_default()


def audio_seconds(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(path),
    ], text=True).strip()
    return float(out)


def speed_audio(src: Path, dest: Path, speed: float = VOICE_SPEED) -> float:
    subprocess.run([
        "ffmpeg", "-y", "-i", str(src), "-filter:a", f"atempo={speed:.3f}",
        "-vn", "-c:a", "libmp3lame", "-b:a", "160k", str(dest),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return audio_seconds(dest)


def fit_cover(src: Path, dest: Path) -> None:
    img = Image.open(src).convert("RGB")
    target_ratio = 1280 / 720
    ratio = img.width / img.height
    if ratio > target_ratio:
        new_h = 720
        new_w = round(new_h * ratio)
    else:
        new_w = 1280
        new_h = round(new_w / ratio)
    img = img.resize((new_w, new_h))
    left = max(0, (new_w - 1280) // 2)
    top = max(0, (new_h - 720) // 2)
    img.crop((left, top, left + 1280, top + 720)).save(dest, quality=95)


def _balanced_chunks(text: str, count: int) -> list[str]:
    words = text.split()
    if count <= 1:
        return [text.strip()]
    chunks: list[str] = []
    start = 0
    for index in range(count):
        remaining_words = len(words) - start
        remaining_chunks = count - index
        take = max(1, round(remaining_words / remaining_chunks))
        end = min(len(words), start + take)
        chunks.append(" ".join(words[start:end]))
        start = end
    if start < len(words):
        chunks[-1] = (chunks[-1] + " " + " ".join(words[start:])).strip()
    return chunks


def _motion_filter(index: int, frames: int) -> str:
    variants = [
        "z='min(zoom+0.0014,1.14)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        f"z='1.12':x='min((iw-iw/zoom)*on/{max(frames,1)},iw-iw/zoom)':y='ih/2-(ih/zoom/2)'",
        f"z='1.12':x='max((iw-iw/zoom)*(1-on/{max(frames,1)}),0)':y='ih/2-(ih/zoom/2)'",
        f"z='1.10':x='iw/2-(iw/zoom/2)':y='min((ih-ih/zoom)*on/{max(frames,1)},ih-ih/zoom)'",
        f"z='1.10':x='iw/2-(iw/zoom/2)':y='max((ih-ih/zoom)*(1-on/{max(frames,1)}),0)'",
    ]
    return variants[index % len(variants)]


def render_scene_fastcuts(
    image_path: Path,
    raw_audio_path: Path,
    narration: str,
    out_dir: Path,
    scene_index: int,
) -> tuple[Path, float, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    fast_audio = out_dir / f"scene-{scene_index:02d}-fast.mp3"
    duration = speed_audio(raw_audio_path, fast_audio)
    shot_count = max(1, math.ceil(duration / SHOT_MAX_SECONDS))
    shot_duration = duration / shot_count
    subtitle_chunks = _balanced_chunks(narration, shot_count)

    frame = out_dir / f"scene-{scene_index:02d}-frame.jpg"
    fit_cover(image_path, frame)
    shot_paths: list[Path] = []

    for shot_index in range(shot_count):
        shot = out_dir / f"scene-{scene_index:02d}-shot-{shot_index+1:02d}.mp4"
        subtitle_file = out_dir / f"scene-{scene_index:02d}-shot-{shot_index+1:02d}.txt"
        subtitle_file.write_text(subtitle_chunks[shot_index], encoding="utf-8")
        frames = max(1, round(shot_duration * VIDEO_FPS))
        motion = _motion_filter(scene_index + shot_index, frames)
        drawtext = (
            f"drawtext=fontfile={FONT_BOLD}:textfile={subtitle_file}:fontcolor=white:fontsize=42:"
            "borderw=5:bordercolor=black:box=1:boxcolor=black@0.34:boxborderw=14:"
            "x=(w-text_w)/2:y=h-text_h-58"
        )
        vf = f"zoompan={motion}:d={frames}:s=1280x720:fps={VIDEO_FPS},{drawtext},format=yuv420p"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(frame), "-vf", vf,
            "-t", f"{shot_duration:.3f}", "-c:v", "libx264", "-preset", "ultrafast",
            "-threads", "1", "-an", str(shot),
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        shot_paths.append(shot)

    concat_file = out_dir / f"scene-{scene_index:02d}-shots.txt"
    concat_file.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in shot_paths), encoding="utf-8")
    visuals = out_dir / f"scene-{scene_index:02d}-visuals.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy", str(visuals),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    segment = out_dir / f"scene-{scene_index:02d}-segment.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(visuals), "-i", str(fast_audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", str(segment),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return segment, duration, shot_count


def concat_segments(parts: list[Path], out_dir: Path, dest: Path) -> None:
    concat = out_dir / "final-segments.txt"
    concat.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-c", "copy", "-movflags", "+faststart", str(dest),
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _wrap_thumbnail_text(text: str, max_words_per_line: int = 2) -> list[str]:
    words = text.upper().split()
    lines: list[str] = []
    for index in range(0, len(words), max_words_per_line):
        lines.append(" ".join(words[index:index + max_words_per_line]))
    return lines[:3]


def make_extreme_thumbnail(base: Path, text: str, dest: Path) -> None:
    tmp = dest.with_name(dest.stem + "-base.jpg")
    fit_cover(base, tmp)
    img = Image.open(tmp).convert("RGB")
    img = ImageEnhance.Color(img).enhance(2.35)
    img = ImageEnhance.Contrast(img).enhance(1.55)
    draw = ImageDraw.Draw(img)

    draw.rectangle((0, 0, 1280, 720), fill=(0, 0, 0, 0))
    draw.ellipse((875, 65, 1240, 430), outline=(255, 235, 0), width=24)
    draw.polygon([(835, 525), (1160, 370), (1025, 610)], fill=(255, 40, 20))

    lines = _wrap_thumbnail_text(text, 2)
    max_width = 930
    max_height = 590
    font_size = 160
    while font_size > 70:
        font = _font(font_size)
        boxes = [draw.textbbox((0, 0), line, font=font, stroke_width=10) for line in lines]
        widths = [b[2] - b[0] for b in boxes]
        heights = [b[3] - b[1] for b in boxes]
        total_h = sum(heights) + max(0, len(lines) - 1) * 4
        if max(widths, default=0) <= max_width and total_h <= max_height:
            break
        font_size -= 6

    font = _font(font_size)
    y = 40
    for line_index, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font, stroke_width=11)
        h = bbox[3] - bbox[1]
        shadow_xy = (45, y + 12)
        draw.text(shadow_xy, line, font=font, fill=(0, 0, 0), stroke_width=14, stroke_fill=(0, 0, 0))
        fill = (255, 235, 0) if line_index == 0 else (255, 255, 255)
        draw.text((30, y), line, font=font, fill=fill, stroke_width=11, stroke_fill=(0, 0, 0))
        y += h + 8

    img.save(dest, quality=96)
