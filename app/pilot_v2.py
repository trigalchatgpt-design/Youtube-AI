from __future__ import annotations

import json
from pathlib import Path

from .channels import CHANNELS
from .episode_writer_v2 import write_episode_v2
from .openai_stack import STACK
from .style_v2 import concat_segments, make_extreme_thumbnail, render_scene_fastcuts
from .youtube import find_uploaded_video_by_title, set_thumbnail, upload_video

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs" / "production" / "archivo-v2-ariane501"
MARKER = OUT / "result.json"
CHANNEL = next(c for c in CHANNELS if c["id"] == "archivo")
TOPIC = "Ariane 5 vuelo 501: cuando reutilizar software dejo de ser una ventaja"

APPROVED_FACTS = """
- El vuelo inaugural de Ariane 5 ocurrio el 4 de junio de 1996.
- El vuelo fue normal hasta aproximadamente 36 segundos despues del inicio de la secuencia principal.
- Los dos sistemas de referencia inercial fallaron practicamente al mismo tiempo.
- La perdida de informacion de guiado y actitud hizo que los controles ordenaran movimientos extremos de las toberas; el lanzador se desvio, sufrio cargas aerodinamicas intensas y termino destruyendose.
- La junta de investigacion de ESA y CNES concluyo que la causa estaba en errores de especificacion y diseno del software del sistema de referencia inercial.
- Una funcion de alineacion del sistema inercial era util antes del despegue, pero permanecia activa despues del despegue aunque ya no era necesaria.
- Esa funcion y el comportamiento completo del sistema inercial no habian sido probados en condiciones suficientemente representativas de la trayectoria real de Ariane 5.
- La junta enfatizo que las revisiones y pruebas no incluyeron un analisis y ensayo adecuados del sistema de referencia inercial ni del sistema completo de control de vuelo que pudieran haber detectado el problema.
- Tras el accidente se recomendaron cambios de software, inhibir la funcion de alineacion despues del despegue, evitar apagados del procesador ante ciertos fallos, usar trayectorias reales en pruebas y mejorar el intercambio de informacion entre equipos y niveles del sistema.
- ESA y CNES aceptaron las recomendaciones y reforzaron la revision del software y la representatividad de las pruebas.
- Definicion simple para el video: un sistema de referencia inercial estima orientacion y movimiento usando sensores internos y entrega datos esenciales al guiado del vehiculo.
- Tesis editorial sugerida: reutilizar algo probado no lo vuelve automaticamente seguro en un sistema nuevo; la compatibilidad depende del contexto, de los limites y de como se prueba la integracion completa.
""".strip()

SOURCES = [
    "https://www.esa.int/Newsroom/Press_Releases/Ariane_501_-_Presentation_of_Inquiry_Board_report",
    "https://www.esa.int/Newsroom/Press_Releases/Qualification_of_Ariane-5_plan_of_action_for_a_resumption_of_flights",
]


def _log(stage: str) -> None:
    print(f"V2_ARIANE {stage}", flush=True)


def run_v2_pilot() -> dict:
    _log("start")
    if MARKER.exists():
        return json.loads(MARKER.read_text(encoding="utf-8"))
    if not STACK.enabled:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    OUT.mkdir(parents=True, exist_ok=True)
    _log("script")
    package = write_episode_v2(CHANNEL, TOPIC, APPROVED_FACTS, scene_count=28)
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
            "Voz argentina de divulgacion, agil y natural. Ritmo vivo, aproximadamente un 10 a 15 por ciento mas rapido que una narracion documental tradicional. Muy clara, cercana, sin sonar infantil ni publicitaria.",
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
    }
    MARKER.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    _log("done")
    return result
