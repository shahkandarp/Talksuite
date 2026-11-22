from fastapi import APIRouter, Depends, File, UploadFile, Form
from typing import Optional

from app.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/transcribe", tags=["transcribe"])


@router.post("")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: Optional[str] = Form("en-US"),
    user: User = Depends(get_current_user),
):
    """
    Transcribe an audio file to text using AWS Transcribe Streaming.

    Accepts audio recorded from the browser (typically webm/opus format).
    Returns the transcribed text.

    - file: Audio file (webm, ogg, wav, etc.)
    - language: Language code (default: en-US)
    """
    from app.main import transcribe_client

    audio_bytes = await file.read()

    # Determine encoding from content type
    content_type = file.content_type or ""
    if "webm" in content_type or "opus" in content_type:
        media_encoding = "ogg-opus"
        sample_rate = 48000
    elif "wav" in content_type:
        media_encoding = "pcm"
        sample_rate = 16000
    elif "flac" in content_type:
        media_encoding = "flac"
        sample_rate = 16000
    else:
        # Default to ogg-opus (most browsers use this with MediaRecorder)
        media_encoding = "ogg-opus"
        sample_rate = 48000

    text = await transcribe_client.transcribe_audio(
        audio_bytes=audio_bytes,
        language_code=language or "en-US",
        media_encoding=media_encoding,
        sample_rate=sample_rate,
    )

    return {"text": text}
