"""
Multi-tier response router.

Routes comments through classification, generation, and moderation pipeline.
"""

import time
from dataclasses import dataclass
from typing import List, Optional

import structlog

from src.config import get_response_settings, get_settings
from src.models import (
    GeneratedResponse,
    ProcessedComment,
    ProcessingStatus,
    ResponseTier,
    YouTubeComment,
)
from src.agents.classifier import get_classifier, CommentClassifier
from src.agents.generator import get_generator, ResponseGenerator

logger = structlog.get_logger(__name__)


@dataclass
class ModerationResult:
    """Result of content moderation check."""

    passed: bool
    issues: List[str]
    modified_text: Optional[str] = None


class ContentModerator:
    """
    Content moderation for generated responses.

    Checks for:
    - Inappropriate content
    - Personal information
    - External links
    - Policy violations
    """

    # Words/phrases to flag
    BLOCKED_PATTERNS = [
        "whatsapp",
        "telegram",
        "dm me",
        "personal number",
        "phone number",
        "email me at",
        "competitor",
    ]

    # Sensitive topics requiring review
    SENSITIVE_TOPICS = [
        "illegal",
        "visa fraud",
        "fake documents",
        "guarantee",
        "promise",
        "100%",
    ]

    def moderate(self, response_text: str) -> ModerationResult:
        """
        Check response for policy violations.

        Args:
            response_text: Generated response text

        Returns:
            ModerationResult with pass/fail and issues
        """
        issues = []
        text_lower = response_text.lower()

        # Check blocked patterns
        for pattern in self.BLOCKED_PATTERNS:
            if pattern in text_lower:
                issues.append(f"Contains blocked content: '{pattern}'")

        # Check sensitive topics
        for topic in self.SENSITIVE_TOPICS:
            if topic in text_lower:
                issues.append(f"Contains sensitive topic: '{topic}'")

        # Check for external URLs (except YouTube)
        import re
        urls = re.findall(r'https?://(?!youtube\.com|youtu\.be)\S+', text_lower)
        if urls:
            issues.append(f"Contains external URLs: {urls}")

        # Check response length
        if len(response_text) > 1000:
            issues.append("Response exceeds maximum length")

        passed = len(issues) == 0

        return ModerationResult(
            passed=passed,
            issues=issues,
        )


class CommentRouter:
    """
    Routes comments through the response pipeline.

    Pipeline:
    1. Classify comment (determine tier)
    2. Generate response (template/RAG/LLM)
    3. Moderate response (safety check)
    4. Return processed result
    """

    def __init__(self):
        self.settings = get_settings()
        self.response_settings = get_response_settings()
        self.classifier = get_classifier()
        self.generator = get_generator()
        self.moderator = ContentModerator()

    def process_comment(
        self,
        comment: YouTubeComment,
        video_title: Optional[str] = None,
        skip_moderation: bool = False,
    ) -> ProcessedComment:
        """
        Process a single comment through the full pipeline.

        Args:
            comment: YouTube comment to process
            video_title: Optional video title for context
            skip_moderation: Skip content moderation (for testing)

        Returns:
            ProcessedComment with classification, response, and status
        """
        start_time = time.time()

        try:
            # Step 1: Classify the comment
            classification = self.classifier.classify(comment)

            logger.info(
                "comment_classified",
                comment_id=comment.comment_id,
                type=classification.comment_type.value,
                tier=classification.response_tier.value,
                confidence=classification.confidence,
            )

            # Check if we should skip (spam, etc.)
            if classification.skip_reason:
                return ProcessedComment(
                    comment=comment,
                    classification=classification,
                    response=None,
                    status=ProcessingStatus.SKIPPED,
                    error_message=classification.skip_reason,
                )

            # Step 2: Generate response based on tier
            if classification.response_tier == ResponseTier.TIER_1_TEMPLATE:
                response = self.generator.generate_simple_response(
                    comment, classification
                )
            else:
                response = self.generator.generate(
                    comment, classification, video_title
                )

            # Step 3: Moderate response
            if not skip_moderation and self.response_settings.enable_moderation:
                moderation = self.moderator.moderate(response.response_text)

                if not moderation.passed:
                    logger.warning(
                        "response_moderation_failed",
                        comment_id=comment.comment_id,
                        issues=moderation.issues,
                    )
                    return ProcessedComment(
                        comment=comment,
                        classification=classification,
                        response=response,
                        status=ProcessingStatus.MODERATED,
                        error_message=f"Moderation issues: {moderation.issues}",
                    )

            # Success
            processing_time = (time.time() - start_time) * 1000

            logger.info(
                "comment_processed",
                comment_id=comment.comment_id,
                tier=response.tier_used.value,
                response_length=len(response.response_text),
                total_time_ms=round(processing_time, 2),
            )

            return ProcessedComment(
                comment=comment,
                classification=classification,
                response=response,
                status=ProcessingStatus.RESPONDED,
            )

        except Exception as e:
            logger.error(
                "comment_processing_failed",
                comment_id=comment.comment_id,
                error=str(e),
            )
            return ProcessedComment(
                comment=comment,
                classification=classification if 'classification' in locals() else None,
                response=None,
                status=ProcessingStatus.FAILED,
                error_message=str(e),
            )

    def process_batch(
        self,
        comments: List[YouTubeComment],
        video_title: Optional[str] = None,
    ) -> List[ProcessedComment]:
        """
        Process a batch of comments.

        Args:
            comments: List of comments to process
            video_title: Optional video title

        Returns:
            List of ProcessedComment results
        """
        results = []
        for comment in comments:
            result = self.process_comment(comment, video_title)
            results.append(result)

        # Summary stats
        success = sum(1 for r in results if r.status == ProcessingStatus.RESPONDED)
        skipped = sum(1 for r in results if r.status == ProcessingStatus.SKIPPED)
        failed = sum(1 for r in results if r.status == ProcessingStatus.FAILED)

        logger.info(
            "batch_processed",
            total=len(results),
            success=success,
            skipped=skipped,
            failed=failed,
        )

        return results


# Singleton instance
_router = None


def get_router() -> CommentRouter:
    """Get the singleton router instance."""
    global _router
    if _router is None:
        _router = CommentRouter()
    return _router