"""
AI-powered response generator using Claude LLM.

Dynamically learns channel persona from video transcripts and generates
contextually relevant, personalized responses. No hardcoded channel details.
"""

import time
from typing import Optional

import structlog
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate

from src.config import get_anthropic_settings, get_channel_settings, get_response_settings
from src.models import (
    CommentClassification,
    GeneratedResponse,
    ResponseTier,
    YouTubeComment,
)
from src.rag import get_retriever, RetrievedContext

logger = structlog.get_logger(__name__)


def build_system_prompt(channel_settings, video_context: str = "") -> str:
    """
    Dynamically build system prompt based on channel settings and video context.

    The AI learns the persona from:
    1. Channel settings (name, topics, tone)
    2. Video transcript context (speaking style, terminology)
    """
    return f"""You are responding to YouTube comments as the channel creator.

CHANNEL CONTEXT:
- Creator: {channel_settings.name}
- Languages: {channel_settings.language}
- Topics: {channel_settings.topics}
- Tone: {channel_settings.tone}

VIDEO CONTEXT (learn the speaking style from this):
{video_context if video_context else "No specific video context available."}

YOUR TASK:
Respond to comments authentically as the channel creator. Learn and match the tone/style from the video context above.

GUIDELINES:
1. LANGUAGE: Match the commenter's language. If they use mixed language (like English + regional words), respond similarly.
2. TONE: Be genuine and conversational - not corporate or robotic. Match the creator's natural speaking style.
3. LENGTH: Keep responses concise (2-4 sentences). Don't over-explain.
4. HELPFULNESS: Answer questions accurately using the video context when relevant.
5. PERSONALITY: Be encouraging and supportive. Sound like a real person, not a bot.

AVOID:
- Generic/template-sounding responses
- Excessive emojis
- Promotional language ("subscribe", "like")
- Overly formal corporate speak

Respond naturally as the creator would."""


RESPONSE_PROMPT_TEMPLATE = """COMMENT TO RESPOND TO:
Author: {author_name}
Comment: {comment_text}

CLASSIFICATION:
- Type: {comment_type}
- Sentiment: {sentiment}
- Language: {language}
- Topics: {topics}

Generate a helpful, authentic response. Keep it concise and natural."""


class ResponseGenerator:
    """
    Generates responses to YouTube comments using Claude LLM.

    Features:
    - RAG-enhanced responses with video context
    - Tone matching to channel style
    - Multi-language support (Telugu/English)
    """

    def __init__(self):
        self.anthropic_settings = get_anthropic_settings()
        self.channel_settings = get_channel_settings()
        self.response_settings = get_response_settings()
        self.retriever = get_retriever()
        self._llm = None

    @property
    def llm(self) -> ChatAnthropic:
        """Lazy load the LLM."""
        if self._llm is None:
            logger.info(
                "initializing_llm",
                model=self.anthropic_settings.model,
            )
            self._llm = ChatAnthropic(
                model=self.anthropic_settings.model,
                api_key=self.anthropic_settings.api_key,
                max_tokens=self.anthropic_settings.max_tokens,
                temperature=self.anthropic_settings.temperature,
            )
        return self._llm

    def generate(
        self,
        comment: YouTubeComment,
        classification: CommentClassification,
        video_title: Optional[str] = None,
    ) -> GeneratedResponse:
        """
        Generate a response for a comment.

        Args:
            comment: The YouTube comment to respond to
            classification: Comment classification result
            video_title: Optional video title for context

        Returns:
            GeneratedResponse with generated text and metadata
        """
        start_time = time.time()

        # Get RAG context if using Tier 2 or 3
        context = ""
        rag_used = False
        retrieved_chunks = []

        if classification.response_tier in [ResponseTier.TIER_2_RAG, ResponseTier.TIER_3_LLM]:
            retrieved = self.retriever.retrieve_for_comment(
                comment_text=comment.text,
                video_id=comment.video_id,
            )
            if retrieved.has_context:
                context = self.retriever.format_context_for_llm(retrieved)
                rag_used = True
                retrieved_chunks = retrieved.chunks

        # Build dynamic system prompt with channel context and video content
        system_prompt = build_system_prompt(self.channel_settings, context)

        # Build the prompt
        prompt = ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            HumanMessage(content=RESPONSE_PROMPT_TEMPLATE.format(
                author_name=comment.author.display_name,
                comment_text=comment.text,
                comment_type=classification.comment_type.value,
                sentiment=classification.sentiment.value,
                language=classification.language or "en",
                topics=", ".join(classification.topics) if classification.topics else "general",
            )),
        ])

        # Generate response
        try:
            response = self.llm.invoke(prompt.format_messages())
            response_text = response.content.strip()

            # Ensure response isn't too long
            if len(response_text) > self.response_settings.max_response_length:
                response_text = response_text[:self.response_settings.max_response_length - 3] + "..."

            generation_time = (time.time() - start_time) * 1000

            # Estimate tokens and cost
            input_tokens = len(prompt.format()) // 4  # Rough estimate
            output_tokens = len(response_text) // 4
            total_tokens = input_tokens + output_tokens

            # Claude pricing (approximate)
            cost_estimate = (input_tokens * 0.003 + output_tokens * 0.015) / 1000

            result = GeneratedResponse(
                response_text=response_text,
                tier_used=classification.response_tier,
                model_used=self.anthropic_settings.model,
                rag_context_used=rag_used,
                retrieved_chunks=retrieved_chunks[:3],  # Limit stored chunks
                generation_time_ms=generation_time,
                token_count=total_tokens,
                cost_estimate=cost_estimate,
            )

            logger.info(
                "response_generated",
                tier=classification.response_tier.value,
                rag_used=rag_used,
                response_length=len(response_text),
                generation_time_ms=round(generation_time, 2),
            )

            return result

        except Exception as e:
            logger.error("response_generation_failed", error=str(e))
            raise

    def generate_simple_response(
        self,
        comment: YouTubeComment,
        classification: CommentClassification,
    ) -> GeneratedResponse:
        """
        Generate a simple response for Tier 1 comments.

        Uses a fast, cheap LLM call to generate a brief, contextual response
        that matches the channel's style - no hardcoded templates.
        """
        start_time = time.time()

        # Use Haiku for fast, cheap simple responses
        simple_llm = ChatAnthropic(
            model="claude-3-haiku-20240307",
            api_key=self.anthropic_settings.api_key,
            max_tokens=100,
            temperature=0.7,
        )

        prompt = f"""You are {self.channel_settings.name}, a content creator.
Someone left this comment: "{comment.text}"
Sentiment: {classification.sentiment.value}

Reply with a brief, warm acknowledgment (1 sentence max).
Match their language style. Be genuine, not robotic.
No emojis unless they used them. No "subscribe" or promotional talk."""

        try:
            response = simple_llm.invoke(prompt)
            response_text = response.content.strip().strip('"')

            generation_time = (time.time() - start_time) * 1000

            return GeneratedResponse(
                response_text=response_text,
                tier_used=ResponseTier.TIER_1_TEMPLATE,
                model_used="claude-3-haiku-20240307",
                rag_context_used=False,
                retrieved_chunks=[],
                generation_time_ms=generation_time,
                token_count=len(response_text) // 4,
                cost_estimate=0.0001,  # Haiku is very cheap
            )
        except Exception as e:
            logger.error("simple_response_failed", error=str(e))
            # Fallback to generic
            return GeneratedResponse(
                response_text="Thanks for watching!",
                tier_used=ResponseTier.TIER_1_TEMPLATE,
                model_used=None,
                rag_context_used=False,
                retrieved_chunks=[],
                generation_time_ms=(time.time() - start_time) * 1000,
                token_count=0,
                cost_estimate=0.0,
            )


# Singleton instance
_generator = None


def get_generator() -> ResponseGenerator:
    """Get the singleton generator instance."""
    global _generator
    if _generator is None:
        _generator = ResponseGenerator()
    return _generator