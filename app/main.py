from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from .channels import CHANNELS, BREAKING_NEWS_TEMPLATE
from .pipeline import generate_package, OUT
from .provider import ProviderStatus
from .scheduler import start_scheduler
from .youtube import authorization_url, exchange_code, channel_info

app = FastAPI(title="YouTube AI Studio", version="0.4.0")

@app.on_event("startup")
def _startup():
    start_scheduler()

class GenerateReq(BaseModel):
    topic: str | None = None

@app.get("/health")
def health():
    return {"ok": True, "service": "youtube-ai-studio", "version": "0.4.0"}

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

@app.get("/oauth/youtube/start")
def youtube_oauth_start():
    try:
        return RedirectResponse(authorization_url())
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))

@app.get("/oauth/youtube/callback", response_class=HTMLResponse)
def youtube_oauth_callback(code: str, state: str):
    try:
        result = exchange_code(code, state)
    except Exception as exc:
        raise HTTPException(400, f"OAuth failed: {exc}")
    persisted = not bool(result.get("refresh_token"))
    return f"<html><body style='font-family:system-ui;max-width:760px;margin:60px auto'><h1>YouTube conectado</h1><p>La autorizacion se completo.</p><p>Para automatizacion permanente, el refresh token debe quedar guardado como variable segura en Railway.</p><p>Ya podes cerrar esta ventana.</p></body></html>"

@app.get("/api/youtube/channel")
def youtube_channel():
    try:
        return channel_info()
    except Exception as exc:
        raise HTTPException(503, str(exc))

@app.get("/", response_class=HTMLResponse)
def dashboard():
    status = ProviderStatus().as_dict()
    cards = "".join(f"<article><h2>{c['name']}</h2><p>{c['tagline']}</p><code>{c['id']}</code></article>" for c in CHANNELS)
    oauth = "<a href='/oauth/youtube/start'>Conectar YouTube</a>" if status['youtube_oauth_configured'] and not status['youtube_connected'] else ("YouTube conectado" if status['youtube_connected'] else "Faltan credenciales OAuth de Google")
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>YouTube AI Studio</title><style>body{{font-family:system-ui;background:#111;color:#eee;max-width:1050px;margin:40px auto;padding:0 20px}}a{{color:#8ec5ff}}section{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}article{{border:1px solid #444;border-radius:18px;padding:20px;background:#181818}}code{{background:#262626;padding:4px 7px;border-radius:6px}}.box{{margin:24px 0;padding:16px;background:#181818;border-radius:14px}}</style></head><body><h1>YouTube AI Studio</h1><p>Orquestador V0.4</p><div class='box'><strong>Estado:</strong><pre>{status}</pre><p>{oauth}</p></div><section>{cards}</section><div class='box'><strong>Contexto Ahora</strong><p>Desactivado hasta conectar fuentes en tiempo real y doble verificacion.</p></div></body></html>"""
