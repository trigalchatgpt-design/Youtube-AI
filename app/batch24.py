from __future__ import annotations

import json
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

from .channels import CHANNELS
from .episode_writer import write_episode_package
from .hubble_episode import run_hubble_private_episode
from .openai_stack import STACK
from .youtube import find_uploaded_video_by_title, set_thumbnail, upload_video

ROOT = Path(__file__).resolve().parents[1]
CHANNEL = next(c for c in CHANNELS if c["id"] == "archivo")
SCENE_COUNT = 24

EPISODES = [
    {
        "key": "apollo13",
        "topic": "Apollo 13: la cadena de fallas dentro del tanque de oxigeno",
        "facts": """
- Apollo 13 despego el 11 de abril de 1970 con destino a la Luna.
- El 13 de abril de 1970, aproximadamente 55 horas y 55 minutos despues del lanzamiento, una explosion afecto el modulo de servicio cuando la nave estaba a unas 205.000 millas de la Tierra.
- La investigacion de NASA se concentro en el tanque de oxigeno numero 2 del modulo de servicio.
- Los tanques de oxigeno contenian calentadores, ventiladores, indicadores de temperatura y sistemas de llenado y drenaje.
- El conjunto de tanques que luego volo en Apollo 13 habia sido retirado previamente de otro modulo y durante ese proceso fue dejado caer aproximadamente dos pulgadas; el incidente fue registrado.
- En pruebas posteriores en tierra, el tanque numero 2 presento dificultades para vaciarse mediante el sistema normal y se usaron calentadores durante un periodo prolongado para eliminar el oxigeno restante.
- La investigacion concluyo que una combinacion de cambios de voltaje de tierra, termostatos no actualizados y calentamiento prolongado pudo danar el aislamiento de teflon de cables internos del tanque.
- Menos de dos minutos antes de la explosion, Control de Mision pidio encender los ventiladores de los tanques para mezclar los fluidos criogenicos.
- La investigacion concluyo que probablemente se produjo un cortocircuito y una chispa dentro del tanque, seguida por un evento de combustion y perdida de integridad del tanque.
- La perdida de oxigeno afecto a las pilas de combustible y obligo a abandonar el alunizaje y concentrarse en traer a la tripulacion de regreso con vida.
- La junta investigadora describio el accidente como el resultado de una combinacion inusual de errores junto con un diseno deficiente y poco tolerante a fallas.
- Para Apollo 14 y misiones posteriores NASA redisenio el sistema de almacenamiento de oxigeno, mejoro termostatos, elimino ventiladores de mezcla y reforzo el cableado.
- El episodio debe enfocarse en como una cadena de decisiones de fabricacion, pruebas, compatibilidad electrica y validacion termino convergiendo en vuelo.
""".strip(),
        "sources": [
            "https://www.nasa.gov/history/50-years-ago-apollo-13-review-board-report/",
            "https://history.nasa.gov/afj/ap13fj/pdf/a13-review-report.pdf",
        ],
    },
    {
        "key": "tacoma",
        "topic": "Tacoma Narrows: el puente que empezo a galopar con el viento",
        "facts": """
- El primer puente Tacoma Narrows abrio al trafico el 1 de julio de 1940 en el estado de Washington.
- En ese momento era el tercer puente colgante de mayor longitud del mundo.
- Desde la etapa final de construccion, trabajadores e ingenieros observaron movimientos verticales ondulatorios del tablero y el puente recibio el apodo Galloping Gertie.
- Se intentaron medidas para reducir el movimiento, entre ellas amortiguadores hidraulicos, sin eliminar el problema.
- El 7 de noviembre de 1940 fuertes vientos cruzados soplaron sobre el estrecho; WSDOT registra mediciones de alrededor de 38 a 42 millas por hora en distintos momentos y lugares.
- Durante la manana el movimiento del puente cambio desde las oscilaciones verticales habituales hacia una torsion violenta del tablero.
- El tramo central termino colapsando y cayendo al agua.
- El puente habia estado abierto apenas cuatro meses.
- Investigaciones posteriores identificaron la excesiva flexibilidad del puente como un factor principal y el caso impulso una nueva comprension del efecto del viento sobre puentes colgantes.
- El colapso tuvo una influencia duradera sobre el diseno aerodinamico y estructural de puentes de gran luz.
- El episodio debe explicar que la historia suele simplificarse como un caso de resonancia, mientras que el fenomeno observado involucraba interaccion aeroelastica y torsion inducida por el viento; evitar reducir la explicacion a una sola frecuencia resonante.
- El eje editorial debe mostrar como una estructura elegante y eficiente puede tener un comportamiento dinamico no previsto si su interaccion con el ambiente no se prueba de manera suficiente.
""".strip(),
        "sources": [
            "https://www.wsdot.wa.gov/TNBhistory/",
            "https://www.wsdot.wa.gov/TNBhistory/collapse.htm",
            "https://www.wsdot.wa.gov/TNBhistory/bridges-failure.htm",
        ],
    },
]


def _log(key: str, stage: str) -> None:
    print(f"BATCH24_{key.upper()} {stage}", flush=True)


def _font(size: int):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def _fit_cover(src: Path, dest: Path) -> None:
    img = Image.open(src).convert("RGB")
    ratio = img.width / img.height
    target_ratio = 1280 / 720
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


def _audio_seconds(path: Path) -> float:
    out = subprocess.check_output([
        "ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)
    ], text=True).strip()
    return float(out)


def _render_moving_segment(image_path: Path, audio_path: Path, dest: Path, index: int) -> float:
    frame = dest.with_suffix(".jpg")
    _fit_cover(image_path, frame)
    seconds = _audio_seconds(audio_path)
    fps = 8
    frames = max(1, int(seconds * fps))
    variants = [
        "z='min(zoom+0.0007,1.10)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'",
        "z='1.08':x='min((iw-iw/zoom)*on/{frames},iw-iw/zoom)':y='ih/2-(ih/zoom/2)'",
        "z='1.08':x='max((iw-iw/zoom)*(1-on/{frames}),0)':y='ih/2-(ih/zoom/2)'",
        "z='1.06':x='iw/2-(iw/zoom/2)':y='min((ih-ih/zoom)*on/{frames},ih-ih/zoom)'",
    ]
    expr = variants[(index - 1) % len(variants)].format(frames=frames)
    vf = f"zoompan={expr}:d={frames}:s=1280x720:fps={fps},format=yuv420p"
    subprocess.run([
        "ffmpeg", "-y", "-loop", "1", "-i", str(frame), "-i", str(audio_path), "-vf", vf,
        "-t", f"{seconds:.3f}", "-c:v", "libx264", "-preset", "ultrafast", "-threads", "1",
        "-c:a", "aac", "-b:a", "160k", "-shortest", str(dest)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return seconds


def _concat(parts: list[Path], out_dir: Path, dest: Path) -> None:
    concat = out_dir / "segments.txt"
    concat.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", "-movflags", "+faststart", str(dest)
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _thumbnail(base: Path, text: str, out_dir: Path, dest: Path) -> None:
    frame = out_dir / "thumb-frame.jpg"
    _fit_cover(base, frame)
    img = Image.open(frame).convert("RGB")
    img = ImageEnhance.Color(img).enhance(2.0)
    img = ImageEnhance.Contrast(img).enhance(1.4)
    draw = ImageDraw.Draw(img)
    draw.ellipse((830, 70, 1225, 470), outline=(255, 235, 0), width=20)
    draw.polygon([(805, 525), (1110, 385), (1015, 575)], fill=(255, 35, 15))
    draw.rounded_rectangle((25, 500, 930, 705), radius=34, fill=(0, 0, 0))
    draw.text((60, 540), text.upper()[:24], font=_font(70), fill=(255, 255, 255))
    img.save(dest, quality=95)


def run_config(config: dict) -> dict:
    key = config["key"]
    out_dir = ROOT / "outputs" / "production" / f"archivo-{key}-24"
    marker = out_dir / "result.json"
    if marker.exists():
        return json.loads(marker.read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)

    _log(key, "script")
    package = write_episode_package(CHANNEL, config["topic"], config["facts"], scene_count=SCENE_COUNT)
    (out_dir / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    duplicate = find_uploaded_video_by_title(package["title"])
    if duplicate:
        result = {"ok": True, "video_id": duplicate["video_id"], "privacy": "existing", "title": package["title"], "deduplicated": True}
        marker.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    segments: list[Path] = []
    total = 0.0
    for index, scene in enumerate(package["scenes"], start=1):
        _log(key, f"scene-{index:02d}")
        audio = out_dir / f"scene-{index:02d}.mp3"
        image = out_dir / f"scene-{index:02d}.png"
        segment = out_dir / f"segment-{index:02d}.mp4"
        STACK.synthesize_speech(scene["narration"], audio, "Voz documental argentina, clara, intrigante y energica. Ritmo medio, diccion muy clara, accesible para publico joven sin infantilizar.")
        STACK.generate_image(scene["visual_prompt"], image, quality="medium")
        total += _render_moving_segment(image, audio, segment, index)
        segments.append(segment)

    video = out_dir / "episode.mp4"
    _concat(segments, out_dir, video)

    _log(key, "thumbnail")
    thumb_base = out_dir / "thumbnail-base.png"
    STACK.generate_image(package["thumbnail_prompt"], thumb_base, quality="medium")
    thumbnail = out_dir / "thumbnail.jpg"
    _thumbnail(thumb_base, package["thumbnail_text"], out_dir, thumbnail)

    description = package["description_intro"].strip() + "\n\nFuentes:\n" + "\n".join(config["sources"]) + "\n\nEste episodio incluye recreaciones visuales generadas por IA."
    _log(key, "youtube-upload")
    uploaded = upload_video(video, package["title"], description, package["tags"], privacy_status="private", category_id="27")
    video_id = uploaded.get("id")
    thumb_result = None
    if video_id:
        try:
            thumb_result = set_thumbnail(video_id, thumbnail)
        except Exception as exc:
            thumb_result = {"warning": str(exc)}

    result = {
        "ok": True,
        "video_id": video_id,
        "privacy": "private",
        "title": package["title"],
        "duration_seconds": round(total, 1),
        "scene_count": len(package["scenes"]),
        "moving_scenes": True,
        "thumbnail": thumb_result,
    }
    marker.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _log(key, "done")
    return result


def run_batch24() -> list[dict]:
    results = []
    results.append(run_hubble_private_episode())
    for config in EPISODES:
        results.append(run_config(config))
    return results
