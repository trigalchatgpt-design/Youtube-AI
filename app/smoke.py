from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .channels import CHANNELS
from .openai_stack import STACK
from .youtube import upload_video, set_thumbnail

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "smoke"
MARKER = OUT / "archivo-private-smoke.json"
CHANNEL_MAP = {c["id"]: c for c in CHANNELS}


def _log(stage: str) -> None:
    print(f"PRIVATE_SMOKE_STAGE {stage}", flush=True)


def _font(size: int):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def _prepare_frame(base_image: Path, dest: Path) -> None:
    img = Image.open(base_image).convert("RGB")
    src_w, src_h = img.size
    target_ratio = 16 / 9
    src_ratio = src_w / src_h
    if src_ratio > target_ratio:
        new_w = int(src_h * target_ratio)
        left = (src_w - new_w) // 2
        img = img.crop((left, 0, left + new_w, src_h))
    else:
        new_h = int(src_w / target_ratio)
        top = (src_h - new_h) // 2
        img = img.crop((0, top, src_w, top + new_h))
    img = img.resize((1280, 720), Image.Resampling.LANCZOS)
    img.save(dest, quality=90, optimize=True)


def _make_thumbnail(base_image: Path, text: str, dest: Path) -> None:
    img = Image.open(base_image).convert("RGB").resize((1280, 720))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((60, 500, 1220, 660), radius=26, fill=(0, 0, 0))
    draw.text((95, 535), text.upper()[:42], font=_font(58), fill=(255, 255, 255))
    img.save(dest, quality=94)


def _render_video(frame_path: Path, audio_path: Path, dest: Path) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-loop", "1", "-framerate", "1", "-i", str(frame_path),
            "-i", str(audio_path),
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-threads", "1", "-r", "1", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart",
            str(dest),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def run_private_smoke() -> dict:
    _log("start")
    if MARKER.exists():
        _log("marker-hit")
        return json.loads(MARKER.read_text(encoding="utf-8"))
    if not STACK.enabled:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    OUT.mkdir(parents=True, exist_ok=True)
    channel = CHANNEL_MAP["archivo"]
    _log("text")
    package = STACK.generate_smoke_package(channel)

    image_path = OUT / "scene.png"
    frame_path = OUT / "frame.jpg"
    audio_path = OUT / "voice.mp3"
    video_path = OUT / "private-smoke.mp4"
    thumb_path = OUT / "thumbnail.jpg"

    _log("image")
    STACK.generate_image(package["image_prompt"], image_path)
    _prepare_frame(image_path, frame_path)
    _log("voice")
    STACK.synthesize_speech(
        package["script"],
        audio_path,
        "Voz documental sobria, intrigante y natural en espanol rioplatense. Ritmo medio, diccion clara, sin dramatizacion excesiva.",
    )
    _log("render")
    _render_video(frame_path, audio_path, video_path)
    _make_thumbnail(frame_path, package["thumbnail_text"], thumb_path)

    description = (
        "PRUEBA TECNICA PRIVADA de YouTube AI Studio para Archivo insolito.\n\n"
        "Este video usa voz generada por IA y fue creado para validar el pipeline tecnico antes de producir episodios reales."
    )
    _log("youtube-upload")
    uploaded = upload_video(
        video_path,
        title=f"[PRUEBA PRIVADA] {package['title']}",
        description=description,
        tags=["prueba privada", "archivo insolito", "youtube ai studio"],
        privacy_status="private",
        category_id="27",
    )
    video_id = uploaded.get("id")
    thumb_result = None
    if video_id:
        _log("thumbnail")
        try:
            thumb_result = set_thumbnail(video_id, thumb_path)
        except Exception as exc:
            thumb_result = {"warning": str(exc)}

    result = {
        "ok": True,
        "video_id": video_id,
        "privacy": "private",
        "title": package["title"],
        "thumbnail": thumb_result,
        "mode": package.get("mode"),
    }
    MARKER.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("done")
    return result
