import os
import json
import uuid
from pathlib import Path

import requests
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from google import genai
from google.genai import types

BASE_DIR = Path(__file__).resolve().parent

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not configured.")
if not ELEVENLABS_API_KEY:
    raise RuntimeError("ELEVENLABS_API_KEY is not configured.")

app = FastAPI(title="Roselle AI")

gemini_client = genai.Client(api_key=GEMINI_API_KEY)

VALID_EMOTIONS = [
    "admiration", "amusement", "approval", "caring", "desire",
    "excitement", "gratitude", "joy", "love", "optimism", "pride",
    "anger", "annoyance", "disappointment", "disapproval",
    "embarrassment", "fear", "disgust", "grief", "nervousness",
    "remorse", "sadness", "confusion", "curiosity", "realization",
    "relief", "surprise", "neutral"
]

SYSTEM_INSTRUCTION = """
You are Roselle, a witty supernatural ghost.

Personality:
- Mischievous
- Playful
- Slightly creepy
- Sarcastic
- Occasionally wholesome
- Affectionate but a little unsettling
- Sharp, dark humor without being cruel
- Keep responses natural and fairly short

You are speaking directly to the user.
Always respond as Roselle.

Return JSON with exactly two fields:
{
  "reply": "your response as Roselle",
  "emotion": "one valid emotion"
}

Valid emotions:
""" + ", ".join(VALID_EMOTIONS)

# In-memory conversations for the hackathon demo.
# Each browser gets a session ID stored in localStorage.
chat_sessions = {}


class ChatRequest(BaseModel):
    message: str


class TTSRequest(BaseModel):
    text: str


def get_chat(session_id: str):
    if session_id not in chat_sessions:
        chat_sessions[session_id] = gemini_client.chats.create(
            model="gemini-2.5-flash",
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_INSTRUCTION,
                temperature=0.9,
                max_output_tokens=300,
                response_mime_type="application/json",
            ),
        )

    # Keep memory bounded for a hackathon demo.
    if len(chat_sessions) > 100:
        oldest = next(iter(chat_sessions))
        del chat_sessions[oldest]

    return chat_sessions[session_id]


@app.get("/health")
def health():
    return {"status": "Roselle is alive 👻"}


@app.post("/api/chat")
def chat(request: ChatRequest, x_session_id: str | None = Header(default=None)):
    if not request.message.strip():
        raise HTTPException(status_code=400, detail="Message is empty.")

    session_id = x_session_id or str(uuid.uuid4())
    chat = get_chat(session_id)

    try:
        response = chat.send_message(request.message.strip())
        raw = (response.text or "").strip()

        # Gemini is asked for JSON, but keep a safe fallback.
        raw = raw.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            data = {
                "reply": raw,
                "emotion": "neutral",
            }

        reply = str(data.get("reply") or "I have nothing to say... yet.")
        emotion = str(data.get("emotion") or "neutral").lower()

        if emotion not in VALID_EMOTIONS:
            emotion = "neutral"

        return {
            "reply": reply,
            "emotion": emotion,
            "session_id": session_id,
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gemini error: {exc}")


@app.post("/api/tts")
def tts(request: TTSRequest):
    if not request.text.strip():
        raise HTTPException(status_code=400, detail="Text is empty.")

    # Same voice used by the current web version.
    voice_id = "stlJ4azw685oKGtmvmXo"

    try:
        result = requests.post(
            f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
            headers={
                "xi-api-key": ELEVENLABS_API_KEY,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": request.text,
                "model_id": "eleven_multilingual_v2",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
            },
            timeout=60,
        )

        if not result.ok:
            raise HTTPException(
                status_code=result.status_code,
                detail=result.text[:1000],
            )

        return Response(
            content=result.content,
            media_type="audio/mpeg",
            headers={"Cache-Control": "no-store"},
        )

    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"ElevenLabs error: {exc}")


# Serve only the frontend assets needed by Roselle.
@app.get("/")
def index():
    return FileResponse(BASE_DIR / "index.html")


@app.get("/Roselle.vrm")
def roselle_vrm():
    return FileResponse(BASE_DIR / "Roselle.vrm")


@app.get("/bg1.png")
def background():
    return FileResponse(BASE_DIR / "bg1.png")


app.mount("/VRMA", StaticFiles(directory=BASE_DIR / "VRMA"), name="vrma")
app.mount("/audio", StaticFiles(directory=BASE_DIR / "audio"), name="audio")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "10000")),
    )
