from __future__ import annotations

BLOCKED_PHRASES = ['garantizado para dormir', 'cura el insomnio', '100% verdadero sin fuentes']

def editorial_gate(channel_id: str, package: dict, source_count: int = 0, confidence: float = 1.0) -> dict:
    text = (package.get('script','') + ' ' + package.get('short_script','')).lower()
    reasons=[]
    if any(p in text for p in BLOCKED_PHRASES):
        reasons.append('claim_bloqueado')
    if channel_id == 'actualidad':
        if source_count < 2: reasons.append('faltan_fuentes')
        if confidence < 0.90: reasons.append('confianza_baja')
    return {'approved': not reasons, 'reasons': reasons}
