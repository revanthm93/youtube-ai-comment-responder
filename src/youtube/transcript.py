"""
YouTube video transcript fetcher.

Uses youtube-transcript-api to fetch video transcripts for RAG indexing.
"""

import re
from typing import List, Optional, Tuple

import structlog
from youtube_transcript_api import (
    YouTubeTranscriptApi,
    NoTranscriptFound,
    TranscriptsDisabled,
    CouldNotRetrieveTranscript,
)

from src.models import VideoTranscript, TranscriptSegment

logger = structlog.get_logger(__name__)


class TranscriptFetchError(Exception):
    """Error fetching transcript."""

    pass


class TranscriptFetcher:
    """
    Fetches and processes YouTube video transcripts.

    Supports multiple languages with preference for Telugu and English.
    """

    # Preferred languages in order of preference
    PREFERRED_LANGUAGES = ["te", "en", "hi", "en-IN"]

    def __init__(self):
        self._api = YouTubeTranscriptApi()

    async def get_transcript(
        self,
        video_id: str,
        languages: Optional[List[str]] = None,
    ) -> VideoTranscript:
        """
        Fetch transcript for a video.

        Args:
            video_id: YouTube video ID
            languages: Preferred languages (uses defaults if not specified)

        Returns:
            VideoTranscript object with segments and full text
        """
        preferred = languages or self.PREFERRED_LANGUAGES

        try:
            # Fetch transcript with preferred languages
            transcript_data = self._api.fetch(video_id, languages=preferred)

            # Determine language from first segment or default
            detected_language = "unknown"
            is_auto_generated = True

            # Parse into segments
            segments = []
            for entry in transcript_data:
                segments.append(
                    TranscriptSegment(
                        text=self._clean_text(entry.text),
                        start=entry.start,
                        duration=entry.duration,
                    )
                )

            # Combine into full text
            full_text = self._combine_segments(segments)

            # Try to get language info from transcript list
            try:
                transcript_list = self._api.list(video_id)
                for t in transcript_list:
                    if t.language_code in preferred:
                        detected_language = t.language_code
                        is_auto_generated = t.is_generated
                        break
                else:
                    # Use first available
                    if transcript_list:
                        detected_language = transcript_list[0].language_code
                        is_auto_generated = transcript_list[0].is_generated
            except Exception:
                pass

            result = VideoTranscript(
                video_id=video_id,
                language=detected_language,
                segments=segments,
                full_text=full_text,
                is_auto_generated=is_auto_generated,
            )

            logger.info(
                "transcript_fetched",
                video_id=video_id,
                language=detected_language,
                segments=len(segments),
                total_chars=len(full_text),
            )

            return result

        except TranscriptsDisabled:
            logger.warning("transcripts_disabled", video_id=video_id)
            raise TranscriptFetchError(f"Transcripts are disabled for video {video_id}")

        except NoTranscriptFound as e:
            logger.warning("no_transcript_found", video_id=video_id, error=str(e))
            raise TranscriptFetchError(f"No transcript found for video {video_id}")

        except CouldNotRetrieveTranscript as e:
            logger.warning("could_not_retrieve_transcript", video_id=video_id)
            raise TranscriptFetchError(f"Could not retrieve transcript for video {video_id}")

        except Exception as e:
            logger.error("transcript_fetch_error", video_id=video_id, error=str(e))
            raise TranscriptFetchError(f"Failed to fetch transcript: {e}")

    def _clean_text(self, text: str) -> str:
        """Clean transcript text."""
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", text)
        # Normalize whitespace
        text = " ".join(text.split())
        return text.strip()

    def _combine_segments(self, segments: List[TranscriptSegment]) -> str:
        """Combine transcript segments into full text."""
        # Group segments into sentences/paragraphs
        sentences = []
        current_sentence = []

        for segment in segments:
            text = segment.text.strip()
            if not text:
                continue

            current_sentence.append(text)

            # Check for sentence endings
            if text.endswith((".", "!", "?", "।")):
                sentences.append(" ".join(current_sentence))
                current_sentence = []

        # Add remaining text
        if current_sentence:
            sentences.append(" ".join(current_sentence))

        return "\n".join(sentences)

    async def get_transcript_chunks(
        self,
        video_id: str,
        chunk_size: int = 500,
        chunk_overlap: int = 50,
    ) -> List[Tuple[str, dict]]:
        """
        Get transcript as chunks for RAG indexing.

        Args:
            video_id: YouTube video ID
            chunk_size: Target characters per chunk
            chunk_overlap: Character overlap between chunks

        Returns:
            List of (chunk_text, metadata) tuples
        """
        transcript = await self.get_transcript(video_id)
        chunks = []

        # Split full text into overlapping chunks
        text = transcript.full_text
        start = 0

        while start < len(text):
            # Find chunk end
            end = start + chunk_size

            # Try to break at sentence boundary
            if end < len(text):
                # Look for sentence end within a window
                window_start = max(start + chunk_size - 100, start)
                window_end = min(start + chunk_size + 100, len(text))
                window = text[window_start:window_end]

                # Find last sentence boundary in window
                for boundary in ["।", ".", "!", "?"]:
                    last_boundary = window.rfind(boundary)
                    if last_boundary != -1:
                        end = window_start + last_boundary + 1
                        break

            chunk_text = text[start:end].strip()

            if chunk_text:
                # Calculate approximate time range for this chunk
                char_ratio = start / len(text) if len(text) > 0 else 0
                total_duration = (
                    transcript.segments[-1].start + transcript.segments[-1].duration
                    if transcript.segments
                    else 0
                )
                approx_start_time = char_ratio * total_duration

                metadata = {
                    "video_id": video_id,
                    "language": transcript.language,
                    "chunk_index": len(chunks),
                    "approx_start_time": approx_start_time,
                    "is_auto_generated": transcript.is_auto_generated,
                }
                chunks.append((chunk_text, metadata))

            start = end - chunk_overlap

        logger.info(
            "transcript_chunked",
            video_id=video_id,
            num_chunks=len(chunks),
            avg_chunk_size=sum(len(c[0]) for c in chunks) / len(chunks) if chunks else 0,
        )

        return chunks

    def check_transcript_available(self, video_id: str) -> bool:
        """Check if a transcript is available for a video."""
        try:
            transcript_list = self._api.list(video_id)
            return len(list(transcript_list)) > 0
        except Exception:
            return False

    def get_available_languages(self, video_id: str) -> List[dict]:
        """Get list of available transcript languages for a video."""
        try:
            transcript_list = self._api.list(video_id)
            return [
                {
                    "language": t.language,
                    "language_code": t.language_code,
                    "is_generated": t.is_generated,
                    "is_translatable": t.is_translatable,
                }
                for t in transcript_list
            ]
        except Exception:
            return []