from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from pathlib import Path

import httpx


def _extract_output_text(payload: dict) -> str:
    if payload.get("output_text"):
        return str(payload["output_text"])
    texts: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(content["text"])
    return "\n".join(texts).strip()


def _json_from_text(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
        text = re.sub(r"\s*```$", "", text)
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        text = text[first:last + 1]
    return json.loads(text)


def _chunks(text: str, limit: int = 3800) -> list[str]:
    paragraphs = [p.strip() for p in text.split("\n") if p.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = (current + "\n\n" + paragraph).strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(paragraph) > limit:
            cut = paragraph.rfind(". ", 0, limit)
            if cut < limit // 2:
                cut = limit
            chunks.append(paragraph[:cut].strip())
            paragraph = paragraph[cut:].strip()
        current = paragraph
    if current:
        chunks.append(current)
    return chunks or [text[:limit]]


class OpenAIStack:
    base_url = "https://api.openai.com/v1"

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY", "").strip()
        self.text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna")
        self.tts_model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
        self.tts_voice = os.getenv("OPENAI_TTS_VOICE", "marin")
        self.image_model = os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2")
        self.image_size = os.getenv("OPENAI_IMAGE_SIZE", "1536x1024")
        self.image_quality = os.getenv("OPENAI_IMAGE_QUALITY", "medium")
        self.timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "180"))

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    def _headers(self) -> dict[str, str]:
        if not self.api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        return {"Authorization": f"Bearer {self.api_key}"}

    def _response_json(self, instructions: str, prompt: str, max_output_tokens: int) -> dict:
        response = httpx.post(
            f"{self.base_url}/responses",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={
                "model": self.text_model,
                "instructions": instructions,
                "input": prompt,
                "max_output_tokens": max_output_tokens,
                "store": False,
                "text": {"verbosity": "medium"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return _json_from_text(_extract_output_text(response.json()))

    def generate_smoke_package(self, channel: dict) -> dict:
        package = self._response_json(
            instructions=(
                "Sos editor de un canal de YouTube en espanol. Esta es una prueba tecnica privada. "
                "No incluyas hechos historicos, datos externos, citas, fechas ni afirmaciones verificables. "
                "El texto debe ser original. Devuelve EXCLUSIVAMENTE JSON valido."
            ),
            prompt=f"""
Canal: {channel['name']}
Propuesta: {channel['tagline']}
Tono: {channel['voice']}
Estilo visual: {channel['visual']}

Genera exactamente estas claves:
- title: titulo breve para una PRUEBA PRIVADA, maximo 80 caracteres.
- script: 90 a 130 palabras presentando el espiritu del canal sin contar ningun hecho real concreto.
- thumbnail_text: 2 a 4 palabras.
- image_prompt: una escena cinematografica 16:9 sin texto, con archivo documental, tecnologia y misterio sobrio; sin logos ni marcas.
""",
            max_output_tokens=900,
        )
        required = {"title", "script", "thumbnail_text", "image_prompt"}
        missing = required - set(package)
        if missing:
            raise RuntimeError(f"Smoke package missing fields: {sorted(missing)}")
        package["mode"] = "openai-smoke"
        return package

    def generate_sourced_episode(self, channel: dict, topic: str, approved_facts: str, scene_count: int = 5) -> dict:
        package = self._response_json(
            instructions=(
                "Sos el guionista principal de un canal documental de YouTube en espanol rioplatense. "
                "Trabajas con un brief factual cerrado. Usa solamente los hechos incluidos en el brief para afirmaciones concretas. "
                "No agregues cifras, fechas, nombres, causas, citas ni detalles tecnicos que no esten en el brief. "
                "No inventes citas. Distingui hechos de interpretacion. Escribi con ritmo narrativo, sobrio e intrigante. "
                "Cada escena debe aportar informacion nueva. Devuelve EXCLUSIVAMENTE JSON valido."
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
Genera un episodio documental de 7 a 10 minutos, original y apto para YouTube. El eje editorial debe mostrar como una incompatibilidad aparentemente pequena puede transformarse en una falla sistemica cuando interfaces, validacion y comunicacion no detectan el problema.

Devuelve exactamente estas claves:
- title: titulo atractivo, preciso, maximo 85 caracteres.
- description_intro: dos parrafos breves para la descripcion, sin URLs.
- thumbnail_text: 2 a 5 palabras, fuerte y legible.
- tags: lista de 8 a 12 etiquetas.
- short_title: titulo para un Short derivado.
- short_script: 100 a 140 palabras, autosuficiente.
- scenes: lista de exactamente {scene_count} objetos. Cada objeto debe tener:
  - heading: titulo interno de escena, 2 a 6 palabras.
  - narration: 150 a 210 palabras.
  - visual_prompt: prompt cinematografico 16:9 sin texto incrustado, sin logos, sin marcas, sin personas famosas; recreacion documental estilizada coherente con la narracion.

La narracion total debe ser continua: gancho inicial, contexto, mecanismo del error, por que no fue detectado, consecuencias y leccion de ingenieria/sistemas. No uses frases de relleno ni repitas la misma idea en varias escenas.
""",
            max_output_tokens=6500,
        )
        required = {"title", "description_intro", "thumbnail_text", "tags", "short_title", "short_script", "scenes"}
        missing = required - set(package)
        if missing:
            raise RuntimeError(f"Sourced episode missing fields: {sorted(missing)}")
        scenes = package.get("scenes") or []
        if len(scenes) != scene_count:
            raise RuntimeError(f"Expected {scene_count} scenes, got {len(scenes)}")
        for index, scene in enumerate(scenes, start=1):
            if not all(key in scene for key in ("heading", "narration", "visual_prompt")):
                raise RuntimeError(f"Scene {index} is incomplete")
        package["mode"] = "openai-sourced"
        return package

    def generate_editorial_package(self, channel: dict, topic: str) -> dict:
        package = self._response_json(
            instructions=(
                "Sos el editor principal de un canal de YouTube en espanol. "
                "El contenido debe ser original, sustantivo, apto para monetizacion y no repetitivo. "
                "Evita relleno, afirmaciones no verificables y citas inventadas. "
                "Devuelve EXCLUSIVAMENTE JSON valido."
            ),
            prompt=f"""
Canal: {channel['name']}
Propuesta: {channel['tagline']}
Idioma: {channel['language']}
Tono: {channel['voice']}
Estilo visual: {channel['visual']}
Pilares: {', '.join(channel['pillars'])}
Reglas: {', '.join(channel['safety'])}
Tema: {topic}

Genera un paquete editorial con estas claves:
- title: titulo de YouTube, maximo 85 caracteres.
- description: 2 a 4 parrafos; si es factual termina con el encabezado Fuentes:.
- tags: lista de 8 a 15 etiquetas.
- hook: apertura de 1 a 3 frases.
- script: guion completo pensado para 6 a 12 minutos; dormir puede ser mas largo.
- short_title: titulo de Short.
- short_script: guion autosuficiente de 35 a 55 segundos con gancho, desarrollo, revelacion y cierre.
- visual_prompts: 6 prompts visuales cinematograficos 16:9 coherentes, sin texto incrustado.
- short_visual_prompts: 3 prompts visuales 9:16, sin texto incrustado.
- thumbnail_prompt: prompt 16:9 simple, foco claro y espacio para titular.
- thumbnail_text: entre 2 y 5 palabras.
- factual: booleano.
- fact_check_notes: lista de afirmaciones que deben verificarse antes de publicar; vacia si es ficcion.
""",
            max_output_tokens=7000,
        )
        required = {"title", "description", "script", "short_script", "visual_prompts", "short_visual_prompts"}
        missing = required - set(package)
        if missing:
            raise RuntimeError(f"OpenAI package missing fields: {sorted(missing)}")
        package["mode"] = "openai"
        return package

    def synthesize_speech(self, text: str, dest: Path, instructions: str) -> str:
        dest.parent.mkdir(parents=True, exist_ok=True)
        parts: list[Path] = []
        for index, chunk in enumerate(_chunks(text)):
            part = dest.with_name(f"{dest.stem}.part{index:02d}.mp3")
            response = httpx.post(
                f"{self.base_url}/audio/speech",
                headers={**self._headers(), "Content-Type": "application/json"},
                json={
                    "model": self.tts_model,
                    "voice": self.tts_voice,
                    "input": chunk,
                    "instructions": instructions,
                    "response_format": "mp3",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            part.write_bytes(response.content)
            parts.append(part)
        if len(parts) == 1:
            parts[0].replace(dest)
            return str(dest)
        concat_file = dest.with_suffix(".concat.txt")
        concat_file.write_text("\n".join(f"file '{p.resolve().as_posix()}'" for p in parts), encoding="utf-8")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(dest)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        for part in parts:
            part.unlink(missing_ok=True)
        concat_file.unlink(missing_ok=True)
        return str(dest)

    def generate_image(self, prompt: str, dest: Path, size: str | None = None, quality: str | None = None) -> str:
        dest.parent.mkdir(parents=True, exist_ok=True)
        response = httpx.post(
            f"{self.base_url}/images/generations",
            headers={**self._headers(), "Content-Type": "application/json"},
            json={
                "model": self.image_model,
                "prompt": prompt,
                "size": size or self.image_size,
                "quality": quality or self.image_quality,
                "output_format": "png",
                "n": 1,
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        item = response.json()["data"][0]
        if item.get("b64_json"):
            dest.write_bytes(base64.b64decode(item["b64_json"]))
        elif item.get("url"):
            image = httpx.get(item["url"], timeout=self.timeout)
            image.raise_for_status()
            dest.write_bytes(image.content)
        else:
            raise RuntimeError("Image API returned neither b64_json nor url")
        return str(dest)


STACK = OpenAIStack()
