from __future__ import annotations

from .openai_stack import STACK


def write_episode_package(channel: dict, topic: str, approved_facts: str, scene_count: int = 24) -> dict:
    target_words = max(45, min(70, round(1320 / max(scene_count, 1))))
    min_words = max(35, target_words - 10)
    max_words = target_words + 12
    last_count = 0

    for attempt in range(2):
        package = STACK._response_json(
            instructions=(
                "Sos el guionista principal de un canal documental de YouTube en espanol rioplatense. "
                "Trabajas con un brief factual cerrado. Usa solamente los hechos incluidos en el brief para afirmaciones concretas. "
                "No agregues cifras, fechas, nombres, causas, citas ni detalles tecnicos que no esten en el brief. "
                "No inventes citas. Distingui hechos, interpretacion y recreacion visual. "
                "Cada escena debe aportar informacion nueva y avanzar el relato. Devuelve EXCLUSIVAMENTE JSON valido."
            ),
            prompt=f"""
CANAL
Nombre: {channel['name']}
Propuesta: {channel['tagline']}
Tono: {channel['voice']}
Visual: {channel['visual']}
Reglas: {', '.join(channel['safety'])}

TEMA
{topic}

BRIEF FACTUAL APROBADO
{approved_facts}

OBJETIVO
Genera un episodio documental original de aproximadamente 8 a 11 minutos. La narracion debe tener ritmo, curiosidad y claridad. El eje editorial tiene que mostrar como decisiones de ingenieria, medicion, interfaces, validacion o comunicacion pueden amplificar un problema y que aprendizaje dejo el caso.

Devuelve exactamente estas claves:
- title: titulo atractivo y preciso, maximo 85 caracteres.
- description_intro: dos parrafos breves para la descripcion, sin URLs.
- thumbnail_text: 2 a 4 palabras, enormes y faciles de leer.
- thumbnail_prompt: prompt de imagen 16:9 SIN texto para una miniatura extremadamente llamativa, estrambotica y apta visualmente para chicos: colores muy saturados, un solo objeto central gigantesco, expresion visual de sorpresa, ciencia/misterio, perspectiva exagerada, luz dramatica, flecha o circulo visual si ayuda, nada de logos, marcas, gore ni personajes con copyright.
- tags: lista de 8 a 12 etiquetas.
- short_title: titulo para un Short derivado.
- short_script: 100 a 140 palabras, autosuficiente.
- scenes: lista de exactamente {scene_count} objetos. Cada objeto debe tener:
  - heading: titulo interno de escena, 2 a 6 palabras.
  - narration: entre {min_words} y {max_words} palabras.
  - visual_prompt: prompt cinematografico 16:9 sin texto incrustado, sin logos, sin marcas, sin personas famosas; recreacion documental estilizada, composicion clara y con profundidad para permitir paneos y zooms de camara.

La narracion total debe ser continua: gancho, contexto, mecanismo, senales previas, punto de falla, consecuencias, investigacion, correccion o aprendizaje. No repitas la misma idea en escenas distintas. No uses frases de relleno.
""",
            max_output_tokens=9000,
        )

        required = {"title", "description_intro", "thumbnail_text", "thumbnail_prompt", "tags", "short_title", "short_script", "scenes"}
        missing = required - set(package)
        if missing:
            raise RuntimeError(f"Episode package missing fields: {sorted(missing)}")

        scenes = package.get("scenes") or []
        last_count = len(scenes)
        if len(scenes) >= scene_count:
            package["scenes"] = scenes[:scene_count]
            for index, scene in enumerate(package["scenes"], start=1):
                if not all(key in scene for key in ("heading", "narration", "visual_prompt")):
                    raise RuntimeError(f"Scene {index} is incomplete")
            package["mode"] = "openai-sourced-24"
            return package

    raise RuntimeError(f"Expected at least {scene_count} scenes, got {last_count}")
