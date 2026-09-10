from __future__ import annotations

from .openai_stack import STACK


def write_episode_v2(
    channel: dict,
    topic: str,
    approved_facts: str,
    scene_count: int = 28,
    editorial_direction: str = "",
) -> dict:
    editorial_block = editorial_direction.strip() or (
        "Explicar por que el caso importa hoy, con una tesis clara y comprensible para publico general."
    )
    package = STACK._response_json(
        instructions=(
            "Sos guionista de divulgacion para YouTube en espanol rioplatense. El publico es general. "
            "Usa solo el brief factual para afirmaciones concretas. No inventes cifras, fechas, nombres, citas ni causas. "
            "Explica terminos tecnicos cuando aparecen por primera vez. Cada video debe tener una idea central y una definicion editorial: "
            "ademas de informar, debe explicar que significa el caso y que aprendizaje deja. Distingui con claridad hechos e interpretacion editorial. "
            "Escribi con ritmo, claridad y frases cortas. Devuelve exclusivamente JSON valido."
        ),
        prompt=f"""
CANAL
{channel['name']} — {channel['tagline']}
Tono: cercano, intrigante, claro, energico, no infantil.

TEMA
{topic}

BRIEF FACTUAL APROBADO
{approved_facts}

DIRECCION EDITORIAL
{editorial_block}

FORMATO
- Duracion objetivo: 6 a 9 minutos con voz agil.
- Publico general: no asumir conocimientos previos.
- Introducir definiciones simples dentro del relato.
- Cada bloque debe responder una pregunta concreta.
- Terminar con una tesis propia que diga por que este caso importa hoy.
- La tesis puede interpretar los hechos, pero no debe presentar opiniones como datos historicos.
- Nada de relleno, solemnidad, consignas partidarias o frases institucionales vacias.

Devuelve estas claves:
- title: titulo atractivo y preciso, maximo 85 caracteres.
- description_intro: dos parrafos breves.
- thesis: una frase clara con la idea central del episodio.
- key_definitions: lista de 3 a 5 objetos con term y definition, lenguaje simple.
- thumbnail_text: 3 a 6 palabras; impactante, enorme, curiosidad inmediata, sin clickbait falso.
- thumbnail_prompt: imagen 16:9 SIN texto, extravagante y muy saturada, objeto central enorme, perspectiva exagerada, contraste extremo, sorpresa visual, composicion estilo gran creador de YouTube, fondo simple, espacio visual suficiente para texto gigante; sin logos, marcas ni gore.
- tags: lista de 8 a 12 etiquetas.
- short_title: titulo de Short.
- short_script: 100 a 140 palabras.
- scenes: apunta a {scene_count} objetos con heading, narration y visual_prompt; son aceptables entre 20 y 30 escenas si el relato queda mejor.
  - narration: 35 a 52 palabras.
  - visual_prompt: 16:9, sin texto, cinematografico, claro, con profundidad y elementos grandes; cada escena debe diferenciarse visualmente de la anterior.

Estructura narrativa: gancho -> que paso -> definiciones necesarias -> capacidades que lo hicieron posible -> decision o desafio -> resultado -> que demuestra -> tesis final.
""",
        max_output_tokens=9000,
    )
    required = {"title", "description_intro", "thesis", "key_definitions", "thumbnail_text", "thumbnail_prompt", "tags", "short_title", "short_script", "scenes"}
    missing = required - set(package)
    if missing:
        raise RuntimeError(f"V2 episode missing fields: {sorted(missing)}")
    scenes = package.get("scenes") or []
    if not 20 <= len(scenes) <= 30:
        raise RuntimeError(f"Expected 20 to 30 scenes, got {len(scenes)}")
    package["scenes"] = scenes[:30]
    package["mode"] = "archivo-v2"
    return package
