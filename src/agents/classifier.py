"""
AI-powered comment classifier for multi-tier response routing.

Uses Claude LLM to intelligently classify comments - no hardcoded patterns.
The AI determines comment type, sentiment, complexity, and language dynamically.
"""

import json
import re
from typing import List, Optional

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage

from src.models import (
    CommentClassification,
    CommentType,
    ResponseTier,
    Sentiment,
    YouTubeComment,
)
from src.config import get_anthropic_settings, get_response_settings

logger = structlog.get_logger(__name__)


CLASSIFIER_SYSTEM_PROMPT = """You are a YouTube comment classifier. Analyze comments and return a JSON classification.

Your task: Classify the comment to determine the best response strategy.

Return ONLY valid JSON with these fields:
{
    "comment_type": "simple" | "question" | "complex" | "spam",
    "sentiment": "positive" | "negative" | "neutral" | "mixed",
    "response_tier": 1 | 2 | 3,
    "confidence": 0.0-1.0,
    "language": "en" | "te" | "tenglish" | "other",
    "topics": ["topic1", "topic2"],
    "skip_reason": null | "reason if spam"
}

Classification rules:
- SIMPLE (tier 1): Short appreciation, greetings, emojis only, "first!", generic praise. Use template response.
- QUESTION (tier 2): Asks for information, advice, clarification. Needs contextual response.
- COMPLEX (tier 3): Multiple questions, detailed situation, comparison requests, step-by-step guidance needed.
- SPAM: Self-promotion, external links, irrelevant marketing.

Language detection:
- "en": Pure English
- "te": Telugu script
- "tenglish": Telugu words written in English script (ela, enti, cheppandi, vuntunda, etc.)
- "other": Other languages

Be smart about detecting questions even without "?" - many users ask in statement form.
Detect Tenglish (Telugu in English script) - common in Indian YouTube comments."""


class CommentClassifier:
    """
    AI-powered comment classifier using Claude.

    No hardcoded patterns - the LLM intelligently determines:
    - Comment type (simple, question, complex, spam)
    - Sentiment (positive, neutral, negative, mixed)
    - Response tier (1=template, 2=RAG, 3=full LLM)
    - Language (English, Telugu, Tenglish)
    - Topics mentioned
    """

    def __init__(self):
        self.settings = get_response_settings()
        self.anthropic_settings = get_anthropic_settings()
        self._llm = None

    @property
    def llm(self) -> ChatAnthropic:
        """Lazy load a fast, cheap model for classification."""
        if self._llm is None:
            self._llm = ChatAnthropic(
                model="claude-3-haiku-20240307",  # Fast & cheap for classification
                api_key=self.anthropic_settings.api_key,
                max_tokens=256,
                temperature=0.0,  # Deterministic classification
            )
        return self._llm

    def classify(self, comment: YouTubeComment) -> CommentClassification:
        """
        Classify a comment using AI.

        Args:
            comment: YouTube comment to classify

        Returns:
            CommentClassification with type, sentiment, and tier
        """
        text = comment.text.strip()

        # Quick checks for obvious cases (saves API calls)
        if self._is_obvious_simple(text):
            return CommentClassification(
                comment_type=CommentType.SIMPLE,
                sentiment=Sentiment.POSITIVE,
                response_tier=ResponseTier.TIER_1_TEMPLATE,
                confidence=0.95,
            )

        # Use AI for nuanced classification
        try:
            result = self._classify_with_llm(text)
            logger.info(
                "comment_classified_by_ai",
                comment_id=comment.comment_id,
                type=result.comment_type.value,
                tier=result.response_tier.value,
            )
            return result
        except Exception as e:
            logger.error("ai_classification_failed", error=str(e))
            # Fallback: treat as question to be safe
            return CommentClassification(
                comment_type=CommentType.QUESTION,
                sentiment=Sentiment.NEUTRAL,
                response_tier=ResponseTier.TIER_2_RAG,
                confidence=0.5,
            )

    def _is_obvious_simple(self, text: str) -> bool:
        """Quick check for obviously simple comments (saves API calls)."""
        text_clean = text.strip().lower()

        # Only emojis
        if re.match(r"^[\U0001F300-\U0001FAFF\s]+$", text):
            return True

        # Very short (1-2 words) positive words
        if len(text.split()) <= 2:
            simple_words = {"thanks", "thank", "great", "nice", "good", "awesome",
                          "super", "excellent", "first", "1st", "liked", "subscribed"}
            if any(w in text_clean for w in simple_words):
                return True

        return False

    def _classify_with_llm(self, text: str) -> CommentClassification:
        """Use Claude to classify the comment."""
        messages = [
            SystemMessage(content=CLASSIFIER_SYSTEM_PROMPT),
            HumanMessage(content=f"Classify this YouTube comment:\n\n\"{text}\""),
        ]

        response = self.llm.invoke(messages)
        content = response.content.strip()

        # Parse JSON response
        # Handle markdown code blocks if present
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        data = json.loads(content)

        # Map response to enums
        type_map = {
            "simple": CommentType.SIMPLE,
            "question": CommentType.QUESTION,
            "complex": CommentType.COMPLEX,
            "spam": CommentType.SPAM,
        }

        sentiment_map = {
            "positive": Sentiment.POSITIVE,
            "negative": Sentiment.NEGATIVE,
            "neutral": Sentiment.NEUTRAL,
            "mixed": Sentiment.MIXED,
        }

        tier_map = {
            1: ResponseTier.TIER_1_TEMPLATE,
            2: ResponseTier.TIER_2_RAG,
            3: ResponseTier.TIER_3_LLM,
        }

        return CommentClassification(
            comment_type=type_map.get(data.get("comment_type", "question"), CommentType.QUESTION),
            sentiment=sentiment_map.get(data.get("sentiment", "neutral"), Sentiment.NEUTRAL),
            response_tier=tier_map.get(data.get("response_tier", 2), ResponseTier.TIER_2_RAG),
            confidence=float(data.get("confidence", 0.8)),
            language=data.get("language", "en"),
            topics=data.get("topics", []),
            skip_reason=data.get("skip_reason"),
        )


# Singleton instance
_classifier = None


def get_classifier() -> CommentClassifier:
    """Get the singleton classifier instance."""
    global _classifier
    if _classifier is None:
        _classifier = CommentClassifier()
    return _classifier