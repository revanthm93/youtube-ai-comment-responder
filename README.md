# YouTube AI Comment Responder

A production-grade AI system that automatically responds to YouTube comments using RAG (Retrieval Augmented Generation) and LLM with multi-tier response strategies.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           YouTube AI Comment Responder                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────────────────────┐│
│  │   FastAPI    │────▶│    Celery    │────▶│      Comment Processor       ││
│  │   REST API   │     │   Workers    │     │                              ││
│  └──────────────┘     └──────────────┘     │  ┌────────┐  ┌────────────┐ ││
│         │                    │              │  │Classify│─▶│ Route Tier │ ││
│         │                    │              │  └────────┘  └────────────┘ ││
│         ▼                    ▼              │       │            │        ││
│  ┌──────────────┐     ┌──────────────┐     │       ▼            ▼        ││
│  │   YouTube    │     │    Redis     │     │  ┌─────────────────────────┐││
│  │   Data API   │     │   Broker     │     │  │    Response Tiers       │││
│  └──────────────┘     └──────────────┘     │  │  ┌─────┐ ┌─────┐ ┌────┐│││
│         │                                   │  │  │ T1  │ │ T2  │ │ T3 ││││
│         │                                   │  │  │Tmpl │ │RAG  │ │LLM ││││
│         ▼                                   │  │  └─────┘ └─────┘ └────┘│││
│  ┌──────────────┐                          │  └─────────────────────────┘││
│  │  Transcript  │                          └──────────────────────────────┘│
│  │   Fetcher    │                                        │                 │
│  └──────────────┘                                        ▼                 │
│         │                                   ┌──────────────────────────────┐│
│         ▼                                   │     Content Moderation       ││
│  ┌──────────────┐     ┌──────────────┐     └──────────────────────────────┘│
│  │   ChromaDB   │◀───▶│  Embeddings  │                   │                 │
│  │ Vector Store │     │  (RAG)       │                   ▼                 │
│  └──────────────┘     └──────────────┘     ┌──────────────────────────────┐│
│                                            │     Post Reply to YouTube     ││
│  ┌──────────────┐     ┌──────────────┐     └──────────────────────────────┘│
│  │  PostgreSQL  │     │   Claude     │                                     │
│  │   Database   │     │   (LLM)      │                                     │
│  └──────────────┘     └──────────────┘                                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Features

### Multi-Tier Response Strategy

| Tier | Type | Description | Example |
|------|------|-------------|---------|
| **Tier 1** | Template | Simple comments (thanks, emoji, short praise) | "Thanks!" → "Thank you for watching! 🙏" |
| **Tier 2** | RAG-Enhanced | Questions about video content | "What visa do I need?" → Context-aware response |
| **Tier 3** | Full LLM | Complex, multi-part questions | Detailed career advice → Thoughtful, personalized response |

### Key Capabilities

- **RAG System**: Embeds video transcripts in ChromaDB for contextual responses
- **Smart Classification**: Automatically categorizes comments by type, sentiment, and complexity
- **Quota Management**: Respects YouTube API limits (10,000 units/day)
- **Async Processing**: Celery workers handle comment processing asynchronously
- **Content Moderation**: Safety layer before posting any replies
- **Cost Optimization**: Routes comments to appropriate tiers to minimize LLM costs
- **Structured Logging**: Production-ready observability with structlog
- **Docker Ready**: Full containerization with docker-compose

## Tech Stack

- **Python 3.11+**
- **FastAPI** - REST API backend
- **LangChain** - LLM orchestration
- **Claude (Anthropic)** - Primary LLM
- **ChromaDB** - Vector storage for RAG
- **Celery + Redis** - Async task queue
- **PostgreSQL** - Comment tracking database
- **Docker** - Containerization

## Quick Start

### Prerequisites

- Python 3.11+
- Docker and Docker Compose (for full deployment)
- YouTube Data API v3 credentials
- Anthropic API key

### 1. Clone and Setup

```bash
cd youtube-ai-comment-responder

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
# Required:
# - YOUTUBE_API_KEY
# - YOUTUBE_CLIENT_ID
# - YOUTUBE_CLIENT_SECRET
# - YOUTUBE_REFRESH_TOKEN
# - YOUTUBE_CHANNEL_ID
# - ANTHROPIC_API_KEY
```

### 3. Run Locally (Development)

```bash
# Start Redis (required for Celery)
docker run -d -p 6379:6379 redis:7-alpine

# Run the API server
uvicorn src.api.app:app --reload --port 8000

# In another terminal, start Celery worker
celery -A src.tasks.celery_app worker --loglevel=info
```

### 4. Run with Docker (Production)

```bash
docker-compose -f docker/docker-compose.yml up -d
```

## Project Structure

```
youtube-ai-comment-responder/
├── src/
│   ├── api/              # FastAPI endpoints
│   │   └── app.py        # Main application
│   ├── agents/           # LangChain agents and chains
│   ├── rag/              # Vector store, embeddings, retrieval
│   ├── youtube/          # YouTube API client wrapper
│   │   ├── client.py     # YouTube Data API client
│   │   └── transcript.py # Video transcript fetcher
│   ├── tasks/            # Celery task definitions
│   ├── models/           # Pydantic models
│   │   ├── youtube.py    # YouTube data models
│   │   ├── api.py        # API request/response models
│   │   └── database.py   # SQLAlchemy models
│   └── config/           # Configuration management
│       ├── settings.py   # Pydantic settings
│       └── logging.py    # Structured logging setup
├── tests/                # Pytest tests
│   ├── unit/
│   └── integration/
├── docker/               # Docker configuration
│   ├── Dockerfile
│   └── docker-compose.yml
├── .github/workflows/    # CI/CD pipelines
├── requirements.txt
├── pyproject.toml
├── .env.example
└── README.md
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| GET | `/api/v1/comments` | List processed comments |
| POST | `/api/v1/comments/fetch` | Fetch unanswered comments |
| POST | `/api/v1/comments/process` | Process comments batch |
| POST | `/api/v1/comments/{id}/reply` | Post reply to comment |
| GET | `/api/v1/videos` | List indexed videos |
| POST | `/api/v1/videos/{id}/index` | Index video transcript |
| GET | `/api/v1/quota` | Get quota status |
| GET | `/api/v1/tasks/{id}` | Get task status |

## YouTube API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project
3. Enable YouTube Data API v3
4. Create OAuth 2.0 credentials
5. Add authorized redirect URI: `http://localhost:8080/callback`
6. Generate refresh token using OAuth flow

## Configuration

Key environment variables:

| Variable | Description | Default |
|----------|-------------|---------|
| `YOUTUBE_CHANNEL_ID` | Your YouTube channel ID | Required |
| `ANTHROPIC_MODEL` | Claude model to use | `claude-sonnet-4-20250514` |
| `DRY_RUN` | Don't post replies (testing) | `true` |
| `TIER1_MAX_TOKENS` | Max tokens for Tier 1 comments | `20` |
| `TIER2_RAG_SIMILARITY_THRESHOLD` | RAG similarity threshold | `0.75` |
| `MAX_COMMENTS_PER_BATCH` | Batch size for processing | `50` |

## Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/unit/test_youtube_client.py -v
```

## Cost Optimization

The multi-tier system optimizes costs:

- **Tier 1**: No LLM calls (templates only) - $0
- **Tier 2**: Small context + short response - ~$0.001/comment
- **Tier 3**: Full context + reasoning - ~$0.01/comment

With smart routing, ~60% of comments use Tier 1, ~30% Tier 2, and ~10% Tier 3.

## Channel Context

This system is configured for Revanth's channel:
- **Content**: UAE relocation, IT careers, career guidance
- **Languages**: Telugu + English mix
- **Tone**: Authentic, conversational, helpful
- **Audience**: Telugu-speaking IT professionals

## License

MIT License

## Author

Revanth - Portfolio project demonstrating AI engineering skills