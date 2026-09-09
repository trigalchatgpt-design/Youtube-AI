from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .channels import CHANNELS
from .openai_stack import STACK
from .youtube import find_uploaded_video_by_title, upload_video, set_thumbnail

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "production" / "archivo-hubble-mirror"
MARKER = OUT / "result.json"
CHANNEL = next(c for c in CHANNELS if c["id"] == "archivo")
TOPIC = "El error de 1,3 milimetros que dejo miope al Hubble"

APPROVED_FACTS = """
- El telescopio espacial Hubble fue lanzado el 24 de abril de 1990.
- Poco despues de comenzar las observaciones, las imagenes mostraban estrellas rodeadas por halos borrosos.
- NASA anuncio el 27 de junio de 1990 que el telescopio tenia una aberracion esferica.
- La investigacion determino que el espejo primario tenia la curva incorrecta y era demasiado plano hacia su borde exterior.
- El error de curvatura estaba aproximadamente diez veces por encima de la tolerancia especificada para el diseno.
- El problema se origino durante la fabricacion del espejo: un dispositivo de prueba llamado null corrector habia sido configurado incorrectamente.
- La investigacion encontro que el espaciado de una lente en ese dispositivo estaba desviado 1,3 milimetros.
- Esa configuracion incorrecta hizo que el proceso de pulido produjera un espejo extremadamente liso, pero con una forma equivocada.
- El espejo primario no estaba disenado para ser reemplazado en orbita.
- NASA aprovecho la capacidad de mantenimiento del Hubble para corregir opticamente el defecto.
- La Wide Field and Planetary Camera 2 incorporo optica correctiva para compensar la aberracion.
- El sistema COSTAR utilizo pequenos espejos correctivos para otros instrumentos cientificos.
- Los astronautas instalaron esas soluciones durante la primera mision de mantenimiento en diciembre de 1993.
- Las primeras imagenes posteriores a la reparacion mostraron que la correccion habia funcionado; NASA anuncio en enero de 1994 que la aberracion habia sido corregida con exito.
- El episodio debe enfocarse en metrologia, pruebas, interfaces entre medicion y fabricacion, senales contradictorias y capacidad de disenar sistemas reparables.
""".strip()

SOURCES = [
    "https://science.nasa.gov/mission/hubble/observatory/design/optics/hubbles-mirror-flaw/",
    "https://science.nasa.gov/mission/hubble/overview/the-history-of-hubble/",
    "https://www.nasa.gov/history/hubble/index.html",
]


def _log(stage: str) -> None:
    print(f"HUBBLE_STAGE {stage}", flush=True)


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
    draw.rounded_rectangle((45, 470, 1235, 670), radius=28, fill=(0, 0, 0))
    draw.text((85, 518), text.upper()[:36], font=_font(62), fill=(255, 255, 255))
    img.save(dest, quality=94)


def _audio_seconds(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
    return float(out)


def _render_segment(image_path: Path, audio_path: Path, dest: Path) -> float:
    frame = dest.with_suffix(".jpg")
    _fit_cover(image_path, frame)
    seconds = _audio_seconds(audio_path)
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-framerate", "1", "-i", str(frame), "-i", str(audio_path),
        "-t", f"{seconds:.3f}", "-r", "1", "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
        "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-shortest", str(dest)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return seconds


def _concat_segments(parts: list[Path], dest: Path) -> None:
    concat = OUT / "segments.txt"
    concat.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(dest)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def run_hubble_private_episode() -> dict:
    _log("start")
    if MARKER.exists():
        return json.loads(MARKER.read_text(encoding="utf-8"))
    if not STACK.enabled:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    OUT.mkdir(parents=True, exist_ok=True)
    _log("script")
    package = STACK.generate_sourced_episode(CHANNEL, TOPIC, APPROVED_FACTS, scene_count=10)
    (OUT / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    duplicate = find_uploaded_video_by_title(package["title"])
    if duplicate:
        result = {"ok": True, "video_id": duplicate["video_id"], "privacy": "existing", "title": package["title"], "deduplicated": True}
        MARKER.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    _log("assets")
    segment_paths: list[Path] = []
    images: list[Path] = []
    total_seconds = 0.0
    for index, scene in enumerate(package["scenes"], start=1):
        _log(f"scene-{index:02d}")
        audio = OUT / f"scene-{index:02d}.mp3"
        image = OUT / f"scene-{index:02d}.png"
        segment = OUT / f"segment-{index:02d}.mp4"
        STACK.synthesize_speech(
            scene["narration"],
            audio,
            "Voz documental argentina, sobria e intrigante. Ritmo medio, pausas naturales, diccion clara. Evita tono publicitario o teatral.",
        )
        STACK.generate_image(scene["visual_prompt"], image, quality="medium")
        total_seconds += _render_segment(image, audio, segment)
        images.append(image)
        segment_paths.append(segment)

    _log(f"concat total={total_seconds:.1f}s")
    video = OUT / "episode.mp4"
    _concat_segments(segment_paths, video)

    thumbnail = OUT / "thumbnail.jpg"
    _make_thumbnail(images[0], package["thumbnail_text"], thumbnail)
    description = package["description_intro"].strip() + "\n\nFuentes:\n" + "\n".join(SOURCES) + "\n\nEste episodio incluye recreaciones visuales generadas por IA."

    _log("youtube-upload")
    uploaded = upload_video(video, package["title"], description, package["tags"], privacy_status="private", category_id="27")
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
        "duration_seconds": round(total_seconds, 1),
        "scene_count": len(package["scenes"]),
        "short_title": package["short_title"],
        "short_script": package["short_script"],
        "thumbnail": thumbnail_result,
        "mode": package.get("mode"),
    }
    MARKER.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("done")
    return result
