from __future__ import annotations
import os

from .youtube import connected as youtube_connected, oauth_configured


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


class ProviderStatus:
    def __init__(self):
        self.openai = bool(os.getenv("OPENAI_API_KEY", "").strip())
        self.youtube_oauth_configured = oauth_configured()
        self.youtube_connected = youtube_connected()
        self.autopublish_enabled = _truthy(os.getenv("AUTOPUBLISH"))
        self.production_stack_ready = self.openai and self.youtube_connected
        self.ready_for_autopublish = self.production_stack_ready and self.autopublish_enabled

    def as_dict(self):
        return {
            "openai": self.openai,
            "youtube_oauth_configured": self.youtube_oauth_configured,
            "youtube_connected": self.youtube_connected,
            "production_stack_ready": self.production_stack_ready,
            "autopublish_enabled": self.autopublish_enabled,
            "ready_for_autopublish": self.ready_for_autopublish,
            "text_model": os.getenv("OPENAI_TEXT_MODEL", "gpt-5.6-luna"),
            "tts_model": os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts"),
            "image_model": os.getenv("OPENAI_IMAGE_MODEL", "gpt-image-2"),
            "video_strategy": "generated-images+tts+ffmpeg",
        }
