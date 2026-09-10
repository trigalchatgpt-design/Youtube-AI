from __future__ import annotations

import json
from pathlib import Path

from .channels import CHANNELS
from .episode_writer_v2 import write_episode_v2
from .openai_stack import STACK
from .style_v2 import concat_segments, make_extreme_thumbnail, render_scene_fastcuts
from .youtube import find_uploaded_video_by_title, set_thumbnail, upload_video

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "production" / "archivo-argentina-opal"
MARKER = OUT / "result.json"
CHANNEL = next(c for c in CHANNELS if c["id"] == "archivo")
TOPIC = "OPAL: el reactor nuclear argentino que Australia eligio para reemplazar el suyo"

APPROVED_FACTS = """
- INVAP, empresa tecnologica argentina con sede en Bariloche y origen en el sistema cientifico-tecnologico nacional, construyo para Australia el reactor de investigacion OPAL.
- El proyecto se desarrollo entre 2000 y 2006.
- En la licitacion internacional compitieron tambien empresas o consorcios de paises como Francia, Canada, Alemania y Estados Unidos.
- El OPAL fue construido en Lucas Heights, Nueva Gales del Sur, para ANSTO, la organizacion australiana de ciencia y tecnologia nuclear.
- El reactor fue concebido para investigacion, produccion de radioisotopos y experimentacion con haces de neutrones.
- Su potencia de diseno es de 20 MW.
- En febrero de 2006 ANSTO autorizo el inicio de la etapa A de puesta en marcha, dando por terminadas oficialmente las etapas de ingenieria y construccion.
- El OPAL alcanzo criticidad por primera vez el 12 de agosto de 2006.
- El combustible de siliciuro de uranio cargado para esa etapa fue fabricado por la Comision Nacional de Energia Atomica de Argentina.
- La criticidad significa que comienza una reaccion nuclear en cadena autosostenida de manera controlada; habilita ensayos de baja potencia antes de avanzar progresivamente hasta la potencia nominal.
- El reactor alcanzo por primera vez su potencia de diseno de 20 MW el 3 de noviembre de 2006, hora local australiana.
- La inauguracion oficial se realizo el 20 de abril de 2007 en Lucas Heights, cerca de Sydney.
- INVAP describe al OPAL como una de las exportaciones argentinas mas importantes de tecnologia de avanzada llave en mano.
- La historia del OPAL forma parte de una trayectoria argentina mas amplia en tecnologia nuclear, con capacidades acumuladas en CNEA, INVAP, universidades, institutos y organismos publicos.
- El episodio debe explicar que vender un reactor de investigacion no equivale a exportar una maquina aislada: implica ingenieria, integracion de sistemas, seguridad, licenciamiento, combustible, puesta en marcha, entrenamiento y transferencia de capacidades.
- No presentar la historia como una hazana aislada ni como prueba de autosuficiencia total. La tesis editorial debe mostrar que la autonomia tecnologica se construye acumulando capacidades, coordinando instituciones y entrando en cadenas internacionales desde posiciones de mayor complejidad.
""".strip()

SOURCES = [
    "https://www.invap.com.ar/13-02-2006-se-inicia-la-puesta-en-marcha-del-reactor-opal-en-australia/",
    "https://www.invap.com.ar/12-08-2006-el-reactor-australiano-opal-construido-por-invap-alcanza-el-estado-critico-por-primera-vez/",
    "https://www.invap.com.ar/10-11-2006-reactor-opal-en-sydney-a-plena-potencia/",
    "https://www.invap.com.ar/20-04-2007-inauguracion-oficial-reactor-opal-en-sydney-australia/",
    "https://www.invap.com.ar/en/the-company/our-history/",
]

EDITORIAL = """
Linea editorial compatible con COPO.EX y Renacer: mirar la historia tecnologica argentina desde el interes nacional, la soberania tecnologica y la capacidad de desarrollo. Mostrar la articulacion entre Estado, sistema cientifico, universidades, empresas tecnologicas y formacion de cuadros. Evitar autarquia, nostalgia vacia o propaganda. La idea central debe ser que la soberania se mide tambien por la capacidad de producir conocimiento, hardware e ingenieria que otros paises necesitan, y por sostener instituciones capaces de hacerlo durante decadas. El cierre debe traer la pregunta al presente argentino: que capacidades conviene preservar, escalar y conectar con nuevas agendas como energia, computacion, satelites, IA e industria avanzada.
""".strip()


def _log(stage: str) -> None:
    print(f"ARG_OPAL {stage}", flush=True)


def run_argentina_opal() -> dict:
    _log("start")
    if MARKER.exists():
        return json.loads(MARKER.read_text(encoding="utf-8"))
    if not STACK.enabled:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    OUT.mkdir(parents=True, exist_ok=True)
    _log("script")
    package = write_episode_v2(CHANNEL, TOPIC, APPROVED_FACTS, scene_count=28, editorial_direction=EDITORIAL)
    (OUT / "package.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf-8")

    duplicate = find_uploaded_video_by_title(package["title"])
    if duplicate:
        result = {"ok": True, "video_id": duplicate["video_id"], "privacy": "existing", "title": package["title"], "deduplicated": True}
        MARKER.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        return result

    segments: list[Path] = []
    total_seconds = 0.0
    total_shots = 0
    for index, scene in enumerate(package["scenes"], start=1):
        _log(f"scene-{index:02d}")
        audio = OUT / f"scene-{index:02d}.mp3"
        image = OUT / f"scene-{index:02d}.png"
        STACK.synthesize_speech(
            scene["narration"],
            audio,
            "Voz argentina de divulgacion, agil, clara y natural. Ritmo vivo, aproximadamente un 10 a 15 por ciento mas rapido que una narracion documental tradicional. Cercana, segura, sin solemnidad patriotera ni tono publicitario.",
        )
        STACK.generate_image(scene["visual_prompt"], image, quality="medium")
        segment, seconds, shots = render_scene_fastcuts(image, audio, scene["narration"], OUT, index)
        segments.append(segment)
        total_seconds += seconds
        total_shots += shots

    video = OUT / "episode.mp4"
    _log(f"concat shots={total_shots}")
    concat_segments(segments, OUT, video)

    _log("thumbnail")
    thumb_base = OUT / "thumbnail-base.png"
    STACK.generate_image(package["thumbnail_prompt"], thumb_base, quality="medium")
    thumbnail = OUT / "thumbnail.jpg"
    make_extreme_thumbnail(thumb_base, package["thumbnail_text"], thumbnail)

    definitions = "\n".join(f"- {item['term']}: {item['definition']}" for item in package.get("key_definitions", []))
    description = (
        package["description_intro"].strip()
        + "\n\nIdea central:\n" + package["thesis"].strip()
        + ("\n\nDefiniciones:\n" + definitions if definitions else "")
        + "\n\nFuentes:\n" + "\n".join(SOURCES)
        + "\n\nEste episodio incluye recreaciones visuales generadas por IA."
    )

    _log("youtube-upload")
    uploaded = upload_video(video, package["title"], description, package["tags"], privacy_status="private", category_id="27")
    video_id = uploaded.get("id")
    thumb_result = None
    if video_id:
        _log("thumbnail-upload")
        thumb_result = set_thumbnail(video_id, thumbnail)

    result = {
        "ok": True,
        "video_id": video_id,
        "privacy": "private",
        "title": package["title"],
        "duration_seconds": round(total_seconds, 1),
        "base_scene_count": len(package["scenes"]),
        "visual_shot_count": total_shots,
        "max_shot_seconds": 4.7,
        "subtitles": "burned-in",
        "voice_speed": 1.12,
        "thesis": package["thesis"],
        "thumbnail": thumb_result,
        "series": "Archivo Insolito Argentina",
    }
    MARKER.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("done")
    return result
