import html
import os
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel

from .channels import CHANNELS, BREAKING_NEWS_TEMPLATE
from .pipeline import generate_package, OUT
from .production import run_first_private_episode
from .provider import ProviderStatus
from .scheduler import start_scheduler
from .smoke import run_private_smoke
from .youtube import authorization_url, exchange_code, channel_info

app = FastAPI(title="YouTube AI Studio", version="0.6.0")


def _run_smoke_once():
    try:
        result = run_private_smoke()
        print(f"PRIVATE_SMOKE_RESULT {result}", flush=True)
    except Exception as exc:
        print(f"PRIVATE_SMOKE_ERROR {type(exc).__name__}: {exc}", flush=True)


def _run_first_episode_once():
    try:
        result = run_first_private_episode()
        print(f"PRODUCTION_RESULT {result}", flush=True)
    except Exception as exc:
        print(f"PRODUCTION_ERROR {type(exc).__name__}: {exc}", flush=True)


@app.on_event("startup")
def _startup():
    start_scheduler()
    if os.getenv("RUN_PRIVATE_SMOKE", "").strip().lower() in {"1", "true", "yes", "on"}:
        threading.Thread(target=_run_smoke_once, daemon=True).start()
    if os.getenv("RUN_FIRST_PRIVATE_EPISODE", "").strip().lower() in {"1", "true", "yes", "on"}:
        threading.Thread(target=_run_first_episode_once, daemon=True).start()


class GenerateReq(BaseModel):
    topic: str | None = None


@app.get("/health")
def health():
    return {"ok": True, "service": "youtube-ai-studio", "version": "0.6.0"}


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

    refresh_token = result.get("refresh_token") or ""
    token_block = ""
    if refresh_token:
        escaped = html.escape(refresh_token, quote=True)
        token_block = f"""
        <div style='margin:24px 0;padding:18px;border:1px solid #ccc;border-radius:12px'>
          <h2 style='margin-top:0'>Ultimo paso: guardar acceso permanente</h2>
          <p>Copiá este valor completo y guardalo en Railway como <strong>YOUTUBE_REFRESH_TOKEN</strong>.</p>
          <textarea readonly style='width:100%;min-height:120px;font-family:monospace;font-size:14px;padding:12px;box-sizing:border-box'>{escaped}</textarea>
          <p style='font-size:14px;color:#555'>Este token es una credencial secreta. No lo pegues en chats ni lo compartas.</p>
        </div>
        """
    else:
        token_block = "<p>Google no devolvió un refresh token nuevo. Volvé a iniciar la conexión y aceptá el consentimiento completo.</p>"

    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>YouTube conectado</title></head><body style='font-family:system-ui;max-width:760px;margin:60px auto;padding:0 20px'><h1>YouTube conectado</h1><p>La autorización se completó correctamente.</p>{token_block}<p>Después de guardar la variable, volvé a ChatGPT y escribí <strong>token guardado</strong>.</p></body></html>"""


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
    return f"""<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>YouTube AI Studio</title><style>body{{font-family:system-ui;background:#111;color:#eee;max-width:1050px;margin:40px auto;padding:0 20px}}a{{color:#8ec5ff}}section{{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}}article{{border:1px solid #444;border-radius:18px;padding:20px;background:#181818}}code{{background:#262626;padding:4px 7px;border-radius:6px}}.box{{margin:24px 0;padding:16px;background:#181818;border-radius:14px}}</style></head><body><h1>YouTube AI Studio</h1><p>Orquestador V0.6</p><div class='box'><strong>Estado:</strong><pre>{status}</pre><p>{oauth}</p></div><section>{cards}</section><div class='box'><strong>Contexto Ahora</strong><p>Desactivado hasta conectar fuentes en tiempo real y doble verificación.</p></div></body></html>"""
