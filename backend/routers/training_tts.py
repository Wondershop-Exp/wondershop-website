"""
AI voice for training guides — 2026-11-12, per Shruti: "give an option to
generate the voice via AI as well. it won't be possible for me to speak
everytime. mostly it will be AI generated".

  POST /api/training/tts   {"text": "...", "voice": "female|male", "speed": 1.0}
       -> audio/mpeg (an MP3 the guide page plays and shares to WhatsApp)

Engine:
  1. Google Cloud Text-to-Speech, if Railway has GOOGLE_TTS_API_KEY (official,
     Indian-English Neural2 voices; free tier covers our use).
  2. Otherwise Microsoft Edge's online voices via the `edge-tts` package
     (en-IN Neerja / Prabhat). No key or account needed, but it is an
     unofficial service and could stop working — then add the Google key.

Public (the training pages have no login yet) but rate-limited in
security.py and capped at MAX_CHARS; the same text is served from a small
in-memory cache so replaying / sharing doesn't call the engine again.
"""
import base64
import hashlib
import logging
import os
from collections import OrderedDict

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_CHARS = 12000
VOICES = {
    "female": {"edge": "en-IN-NeerjaNeural", "google": "en-IN-Neural2-A"},
    "male":   {"edge": "en-IN-PrabhatNeural", "google": "en-IN-Neural2-B"},
}
_CACHE: "OrderedDict[str, bytes]" = OrderedDict()
_CACHE_MAX = 40


class TTSRequest(BaseModel):
    text: str
    voice: str = "female"
    speed: float = 1.0


async def _google(text: str, voice: str, speed: float, key: str) -> bytes:
    # Google caps one request at 5000 bytes — split on sentence ends and join the MP3s.
    parts, cur = [], ""
    for sent in text.replace("\n", " ").split(". "):
        piece = (sent.strip() + ". ") if sent.strip() else ""
        if len((cur + piece).encode()) > 4500 and cur:
            parts.append(cur); cur = ""
        cur += piece
    if cur.strip():
        parts.append(cur)
    out = b""
    async with httpx.AsyncClient(timeout=60) as c:
        for p in parts:
            r = await c.post(f"https://texttospeech.googleapis.com/v1/text:synthesize?key={key}", json={
                "input": {"text": p},
                "voice": {"languageCode": "en-IN", "name": VOICES[voice]["google"]},
                "audioConfig": {"audioEncoding": "MP3", "speakingRate": speed},
            })
            if r.status_code != 200:
                raise RuntimeError(f"Google TTS {r.status_code}: {r.text[:200]}")
            out += base64.b64decode(r.json()["audioContent"])
    return out


async def _edge(text: str, voice: str, speed: float) -> bytes:
    import edge_tts   # imported here so the app still starts if the package is missing
    pct = int(round((speed - 1) * 100))
    com = edge_tts.Communicate(text, VOICES[voice]["edge"], rate=f"{pct:+d}%")
    out = bytearray()
    async for chunk in com.stream():
        if chunk.get("type") == "audio":
            out += chunk["data"]
    if not out:
        raise RuntimeError("no audio returned")
    return bytes(out)


@router.post("/training/tts")
async def tts(body: TTSRequest):
    text = " ".join((body.text or "").split())
    if not text:
        raise HTTPException(status_code=400, detail="Nothing to read.")
    if len(text) > MAX_CHARS:
        raise HTTPException(status_code=400, detail="That's too long for one voice note — try one step at a time.")
    voice = body.voice if body.voice in VOICES else "female"
    speed = max(0.7, min(1.4, float(body.speed or 1)))
    ck = hashlib.sha256(f"{voice}|{speed}|{text}".encode()).hexdigest()
    if ck in _CACHE:
        _CACHE.move_to_end(ck)
        audio = _CACHE[ck]
    else:
        key = os.getenv("GOOGLE_TTS_API_KEY", "").strip()
        try:
            audio = await (_google(text, voice, speed, key) if key else _edge(text, voice, speed))
        except Exception as e:
            logger.exception("training TTS failed")
            raise HTTPException(status_code=502, detail=f"Couldn't make the AI voice right now ({e}). Please try again in a minute.")
        _CACHE[ck] = audio
        while len(_CACHE) > _CACHE_MAX:
            _CACHE.popitem(last=False)
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Content-Disposition": 'inline; filename="training-voice.mp3"', "Cache-Control": "private, max-age=86400"})
