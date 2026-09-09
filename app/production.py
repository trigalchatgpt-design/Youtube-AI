from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .channels import CHANNELS
from .openai_stack import STACK
from .youtube import upload_video, set_thumbnail

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "production" / "archivo-mars-climate-orbiter"
MARKER = OUT / "result.json"
CHANNEL = next(c for c in CHANNELS if c["id"] == "archivo")
TOPIC = "El error de unidades que hizo perder la Mars Climate Orbiter"

APPROVED_FACTS = """
- La Mars Climate Orbiter fue una mision de NASA lanzada en 1998 para estudiar Marte y actuar como relevo de comunicaciones.
- La nave se perdio el 23 de septiembre de 1999 durante la insercion orbital alrededor de Marte.
- Una investigacion de NASA determino que el equipo de navegacion trabajaba con datos esperados en unidades metricas, mientras que un sistema entregaba datos de impulso en unidades inglesas de pound-seconds.
- Esa incompatibilidad produjo errores acumulados en la trayectoria estimada.
- La nave paso demasiado cerca de Marte y se perdio; NASA considero que probablemente entro en la atmosfera a una altitud mucho menor que la prevista.
- El incidente se convirtio en un caso clasico de fallas de interfaces, validacion, comunicacion entre equipos y control de sistemas.
- El objetivo editorial del episodio es explicar el mecanismo del error y por que una diferencia de unidades pudo atravesar controles sin ser detectada a tiempo.
""".strip()

SOURCES = [
    "NASA Mars Climate Orbiter Mishap Investigation Board Phase I Report",
    "NASA/JPL mission documentation on Mars Climate Orbiter",
]


def _log(stage: str) -> None:
    print(f"PRODUCTION_STAGE {stage}", flush=True)


def _font(size: int):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def _fit_cover(src: Path, dest: Path) -> None:
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
    img.crop((left, top, left + 1280, top + 720)).save(dest, quality=94)


def _make_thumbnail(base_image: Path, text: str, dest: Path) -> None:
    frame = OUT / "thumb-frame.jpg"
    _fit_cover(base_image, frame)
    img = Image.open(frame).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((55, 480, 1225, 665), radius=30, fill=(0, 0, 0))
    draw.text((90, 520), text.upper()[:38], font=_font(64), fill=(255, 255, 255))
    img.save(dest, quality=94)


def _audio_seconds(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
    return float(out)


def _render_scene(image_path: Path, seconds: float, dest: Path) -> None:
    frame = dest.with_suffix(".jpg")
    _fit_cover(image_path, frame)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-framerate", "1", "-i", str(frame),
        "-t", f"{seconds:.3f}", "-r", "1", "-c:v", "libx264", "-preset", "ultrafast",
        "-threads", "1", "-pix_fmt", "yuv420p", "-an", str(dest)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _concat_video(parts: list[Path], audio: Path, dest: Path) -> None:
    concat = OUT / "video-parts.txt"
    concat.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
    silent = OUT / "silent.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat),
        "-c", "copy", str(silent)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(audio),
        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", str(dest)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_first_private_episode() -> dict:
    _log("start")
    if MARKER.exists():
        _log("marker-hit")
        return json.loads(MARKER.read_text(encoding="utf-8"))
    if not STACK.enabled:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    OUT.mkdir(parents=True, exist_ok=True)
    _log("script")
    package = STACK.generate_sourced_episode(CHANNEL, TOPIC, APPROVED_FACTS, scene_count=5)
    (OUT / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    narration = "\n\n".join(scene["narration"] for scene in package["scenes"])
    audio = OUT / "narration.mp3"
    _log("voice")
    STACK.synthesize_speech(
        narration,
        audio,
        "Voz documental argentina, sobria e intrigante. Ritmo medio, pausas naturales, diccion clara. Evita tono publicitario o teatral.",
    )

    _log("images")
    images: list[Path] = []
    for index, scene in enumerate(package["scenes"], start=1):
        path = OUT / f"scene-{index:02d}.png"
        STACK.generate_image(scene["visual_prompt"], path, quality="medium")
        images.append(path)

    total_seconds = _audio_seconds(audio)
    scene_seconds = max(8.0, total_seconds / len(images))
    _log(f"render total={total_seconds:.1f}s")
    videos: list[Path] = []
    for index, image in enumerate(images, start=1):
        path = OUT / f"scene-{index:02d}.mp4"
        _render_scene(image, scene_seconds + 0.25, path)
        videos.append(path)

    video = OUT / "episode.mp4"
    _concat_video(videos, audio, video)

    thumbnail = OUT / "thumbnail.jpg"
    _make_thumbnail(images[0], package["thumbnail_text"], thumbnail)

    description = (
        package["description_intro"].strip()
        + "\n\nFuentes consultadas:\n- "
        + "\n- ".join(SOURCES)
        + "\n\nEste episodio incluye recreaciones visuales generadas por IA."
    )

    _log("youtube-upload")
    uploaded = upload_video(
        video,
        title=package["title"],
        description=description,
        tags=package["tags"],
        privacy_status="private",
        category_id="27",
    )
    video_id = uploaded.get("id")
    thumbnail_result = None
    if video_id:
        _log("thumbnail")
        try:
            thumbnail_result = set_thumbnail(video_id, thumbnail)
        except Exception as exc:
            thumbnail_result = {"warning": str(exc)}

    result = {
        "ok": True,
        "video_id": video_id,
        "privacy": "private",
        "title": package["title"],
        "short_title": package["short_title"],
        "short_script": package["short_script"],
        "duration_seconds": round(total_seconds, 1),
        "thumbnail": thumbnail_result,
        "mode": package.get("mode"),
    }
    MARKER.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("done")
    return result
