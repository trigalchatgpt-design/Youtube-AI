from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from .channels import CHANNELS, BREAKING_NEWS_TEMPLATE
from .pipeline import generate_package, OUT
from .provider import ProviderStatus
from .scheduler import start_scheduler

app = FastAPI(title="YouTube AI Studio", version="0.3.0")

@app.on_event("startup")
def _startup():
    start_scheduler()

class GenerateReq(BaseModel):
    topic: str | None = None

@app.get("/health")
def health():
    return {"ok": True, "service": "youtube-ai-studio", "version": "0.3.0"}

@app.get("/api/status")
def provider_status():
    return ProviderStatus().as_dict()

@app.get("/api/channels")
def channels():
    return {"channels": CHANNELS, "breaking_news": BREAKING_NEWS_TEMPLATE}

@app.post("/api/generate/{channel_id}")
def generate(channel_id: str, req: GenerateReq):
    if channel_id not in {c["id"] for c in CHANNELS}:
        raise HTTPException(404, "Unknown channel")
    return generate_package(channel_id, req.topic)

@app.get("/api/packages")
def packages():
    items=[]
    if OUT.exists():
        for f in OUT.glob("*/*/package.json"):
            items.append(str(f.parent.relative_to(OUT)))
    return {"packages": sorted(items)}

@app.get("/", response_class=HTMLResponse)
def dashboard():
    cards = "".join(f"<article><h2>{c['name']}</h2><p>{c['tagline']}</p><code>{c['id']}</code></article>" for c in CHANNELS)
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>YouTube AI Studio</title><style>body{{font-family:system-ui;background:#111;color:#eee;max-width:1050px;margin:40px auto;padding:0 20px}}header{{margin-bottom:30px}}section{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}article{{border:1px solid #444;border-radius:18px;padding:20px;background:#181818}}code{{background:#262626;padding:4px 7px;border-radius:6px}}.warn{{margin-top:24px;border-left:4px solid #aaa;padding:12px 16px;background:#181818}}</style></head><body><header><h1>YouTube AI Studio</h1><p>Orquestador V0.3 — identidad, ideacion, guion, thumbnail, render y futura publicacion.</p></header><section>{cards}</section><div class='warn'><strong>Contexto Ahora</strong><p>Preparado pero desactivado hasta conectar fuentes en tiempo real y doble verificacion.</p></div></body></html>"""
