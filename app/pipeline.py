from __future__ import annotations
import json, random, subprocess, time
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from .channels import CHANNELS
from .ideas import IDEAS

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
OUT.mkdir(exist_ok=True)
CHANNEL_MAP = {c["id"]: c for c in CHANNELS}

def _font(size: int):
    for p in ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]:
        if Path(p).exists():
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()

def draft_script(channel_id: str, topic: str | None = None) -> dict:
    c = CHANNEL_MAP[channel_id]
    topic = topic or random.choice(IDEAS[channel_id])
    hook = {
        "dormir": f"Esta noche viajamos a {topic.lower()}, un lugar al que se llega cuando el ruido del dia empieza a apagarse.",
        "matematica": f"Hay un problema clasico que parece decir una cosa y termina demostrando otra: {topic}.",
        "archivo": f"Parece un detalle menor, pero esta historia termino cambiando la forma en que entendemos la tecnologia: {topic}.",
    }[channel_id]
    beats = ["Gancho de 10-20 segundos", "Contexto minimo para entender el problema o mundo", "Desarrollo en tres actos o pasos", "Momento de revelacion", "Cierre que conecta con una idea mas grande"]
    body = "\n\n".join([
        hook,
        f"Contexto: {topic}. El episodio se construye con el tono {c['voice']} y evita relleno repetitivo.",
        "Desarrollo: la narracion avanza por escenas o pasos claros. Cada bloque agrega informacion nueva y mantiene continuidad.",
        "Revelacion: el punto central se explica con una imagen mental concreta y una conclusion verificable cuando corresponde.",
        "Cierre: una frase breve recupera el gancho inicial y deja una pregunta o sensacion que habilita el siguiente episodio.",
    ])
    short = f"{hook} En menos de un minuto te muestro el giro central. [DESARROLLO 35s] [REVELACION 10s] Si queres la historia completa, esta en el canal."
    return {"channel": channel_id, "topic": topic, "hook": hook, "beats": beats, "script": body, "short_script": short, "generated_at": int(time.time()), "mode": "fallback"}

def make_thumbnail(channel_id: str, topic: str, dest: Path) -> str:
    img = Image.new("RGB", (1280, 720), (22, 25, 34))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60, 70, 1220, 650), radius=34, outline=(220, 220, 220), width=4)
    words = topic.upper().split()
    lines, line = [], ""
    for w in words:
        test = (line + " " + w).strip()
        if len(test) > 24:
            lines.append(line); line = w
        else:
            line = test
    if line: lines.append(line)
    y = 165
    for ln in lines[:4]:
        d.text((100, y), ln, font=_font(64), fill=(245,245,245)); y += 82
    d.text((100, 560), CHANNEL_MAP[channel_id]["name"], font=_font(32), fill=(200,200,200))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, quality=94)
    return str(dest)

def render_placeholder_video(channel_id: str, topic: str, script: str, dest: Path, seconds: int = 8) -> str:
    thumb = dest.with_suffix(".png")
    make_thumbnail(channel_id, topic, thumb)
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", str(thumb), "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", str(seconds), "-vf", "scale=1280:720,format=yuv420p", "-c:v", "libx264", "-c:a", "aac", "-shortest", str(dest)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(dest)

def generate_package(channel_id: str, topic: str | None = None) -> dict:
    draft = draft_script(channel_id, topic)
    slug = "".join(ch if ch.isalnum() else "-" for ch in draft["topic"].lower()).strip("-")[:70]
    folder = OUT / channel_id / slug
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "package.json").write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
    make_thumbnail(channel_id, draft["topic"], folder / "thumbnail.jpg")
    render_placeholder_video(channel_id, draft["topic"], draft["script"], folder / "preview.mp4")
    return {**draft, "folder": str(folder), "thumbnail": str(folder / "thumbnail.jpg"), "preview": str(folder / "preview.mp4")}
