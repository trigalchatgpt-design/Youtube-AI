from __future__ import annotations
import os

def _truthy(value: str | None) -> bool:
    return (value or '').strip().lower() in {'1', 'true', 'yes', 'on'}

class ProviderStatus:
    def __init__(self):
        self.openai = bool(os.getenv('OPENAI_API_KEY'))
        self.youtube_oauth = all(bool(os.getenv(key)) for key in ('YOUTUBE_CLIENT_ID', 'YOUTUBE_CLIENT_SECRET', 'YOUTUBE_REFRESH_TOKEN'))
        self.tts = bool(os.getenv('TTS_API_KEY'))
        self.image_video = bool(os.getenv('MEDIA_API_KEY'))
        self.autopublish_enabled = _truthy(os.getenv('AUTOPUBLISH'))

    def as_dict(self):
        production_stack_ready = all([self.openai, self.youtube_oauth, self.tts, self.image_video])
        return {
            'openai': self.openai,
            'youtube_oauth': self.youtube_oauth,
            'tts': self.tts,
            'image_video': self.image_video,
            'production_stack_ready': production_stack_ready,
            'autopublish_enabled': self.autopublish_enabled,
            'ready_for_autopublish': production_stack_ready and self.autopublish_enabled,
        }
