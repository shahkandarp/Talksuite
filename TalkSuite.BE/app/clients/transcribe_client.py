import asyncio
from typing import Optional

from app.config import settings


class TranscribeClient:
    """
    AWS Transcribe Streaming client.

    Accepts audio bytes and returns the transcribed text using
    AWS Transcribe's StartStreamTranscription API.
    Falls back to mock mode when AWS credentials are not configured.
    """

    def __init__(self):
        self._mock_mode = False
        self.client = None

        try:
            import boto3
            # On ECS, the task role provides credentials automatically.
            client_kwargs = {"region_name": settings.aws_region}
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                client_kwargs["aws_access_key_id"] = settings.aws_access_key_id
                client_kwargs["aws_secret_access_key"] = settings.aws_secret_access_key

            self.client = boto3.client("transcribe", **client_kwargs)
            print("[TalkSuite] Transcribe Client initialized")
        except Exception as e:
            self._mock_mode = True
            print(f"[TalkSuite] Transcribe Client running in MOCK mode ({e})")

    async def transcribe_audio(
        self,
        audio_bytes: bytes,
        language_code: str = "en-US",
        media_encoding: str = "ogg-opus",
        sample_rate: int = 48000,
    ) -> str:
        """
        Transcribe audio bytes using AWS Transcribe Streaming.

        Args:
            audio_bytes: Raw audio data (webm/opus from browser MediaRecorder)
            language_code: Language to transcribe (default: en-US)
            media_encoding: Audio encoding format (ogg-opus for browser recordings)
            sample_rate: Audio sample rate in Hz

        Returns:
            Transcribed text string.
        """
        if self._mock_mode:
            return "[MOCK] Voice transcription not available — AWS credentials not configured."

        try:
            from amazon_transcribe.client import TranscribeStreamingClient
            from amazon_transcribe.handlers import TranscriptResultStreamHandler
            from amazon_transcribe.model import TranscriptEvent

            transcript_parts = []

            class EventHandler(TranscriptResultStreamHandler):
                async def handle_transcript_event(self, transcript_event: TranscriptEvent):
                    results = transcript_event.transcript.results
                    for result in results:
                        if not result.is_partial:
                            for alt in result.alternatives:
                                transcript_parts.append(alt.transcript)

            client = TranscribeStreamingClient(region=settings.aws_region)

            stream = await client.start_stream_transcription(
                language_code=language_code,
                media_sample_rate_hz=sample_rate,
                media_encoding=media_encoding,
            )

            # Send audio in chunks
            chunk_size = 1024 * 16  # 16KB chunks
            audio_stream = stream.input_stream
            for i in range(0, len(audio_bytes), chunk_size):
                chunk = audio_bytes[i : i + chunk_size]
                await audio_stream.send_audio_event(audio_chunk=chunk)
            await audio_stream.end_stream()

            # Process results
            handler = EventHandler(stream.output_stream)
            await handler.handle_events()

            return " ".join(transcript_parts).strip() or "Could not transcribe audio."

        except ImportError:
            # Fallback: use boto3 Transcribe with a simpler approach
            return await self._transcribe_with_boto3(
                audio_bytes, language_code, media_encoding, sample_rate
            )
        except Exception as e:
            print(f"[TalkSuite] Transcription failed: {e}")
            return f"Transcription failed: {str(e)}"

    async def _transcribe_with_boto3(
        self,
        audio_bytes: bytes,
        language_code: str,
        media_encoding: str,
        sample_rate: int,
    ) -> str:
        """
        Fallback transcription using boto3's transcribe streaming.
        Uses asyncio.to_thread for the synchronous boto3 client.
        """
        import boto3
        import json
        from botocore.config import Config

        try:
            client = boto3.client(
                "transcribe-streaming",
                region_name=settings.aws_region,
                config=Config(read_timeout=30),
            )

            def do_transcribe():
                # Create audio stream generator
                chunk_size = 1024 * 16

                def audio_stream():
                    for i in range(0, len(audio_bytes), chunk_size):
                        yield {"AudioEvent": {"AudioChunk": audio_bytes[i : i + chunk_size]}}

                response = client.start_stream_transcription(
                    LanguageCode=language_code,
                    MediaEncoding=media_encoding,
                    MediaSampleRateHertz=sample_rate,
                    AudioStream=audio_stream(),
                )

                # Collect results
                transcript_parts = []
                for event in response["TranscriptResultStream"]:
                    if "TranscriptEvent" in event:
                        results = event["TranscriptEvent"]["Transcript"]["Results"]
                        for result in results:
                            if not result["IsPartial"]:
                                for alt in result["Alternatives"]:
                                    transcript_parts.append(alt["Transcript"])

                return " ".join(transcript_parts).strip()

            result = await asyncio.to_thread(do_transcribe)
            return result or "Could not transcribe audio."

        except Exception as e:
            print(f"[TalkSuite] Boto3 transcription failed: {e}")
            return f"Transcription failed: {str(e)}"
