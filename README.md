# YouTube AI Studio

Base operativa para una red de canales de YouTube asistidos por IA.

## Canales iniciales
- **Buenas Noches, Mundo** — historias originales para dormir.
- **Mate Exacto** — matematica visual y problemas clasicos.
- **Archivo Insolito** — historias reales sobre tecnologia, exploracion e infraestructura.
- **Contexto Ahora** — breaking news, preparado pero desactivado hasta conectar fuentes y verificacion en tiempo real.

## Lo que ya funciona sin credenciales externas
- Configuracion editorial por canal.
- Banco inicial de temas.
- Generacion deterministica de paquetes de contenido.
- Guion base + version Short.
- Thumbnail 1280x720.
- Render MP4 de previsualizacion con FFmpeg.
- API FastAPI y dashboard.
- Dockerfile listo para Railway.

## Lo que se activa al agregar credenciales
- `OPENAI_API_KEY`: guiones, variaciones, QA y metadatos con modelos.
- proveedor de TTS: voz natural.
- proveedor de imagen/video: escenas y B-roll generativo.
- OAuth YouTube: crear/subir/programar videos, miniaturas, playlists y Shorts.
- fuentes de noticias: modulo `Contexto Ahora` con doble verificacion.

## API
- `GET /health`
- `GET /api/status`
- `GET /api/channels`
- `POST /api/generate/{channel_id}` body `{ "topic": "..." }`
- `GET /api/packages`

## Desarrollo
```bash
pip install -r requirements.txt
uvicorn app.main:app --reload
```
