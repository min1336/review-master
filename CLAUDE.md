# Review Summary AI

AI-powered review summarization system for Carmore car rental company.

## Tech Stack

- **Backend**: Python 3.x, Flask
- **NLP**: MeCab (Korean morphology), BERT (sentiment), Lexicon-based analysis
- **LLM**: OpenAI GPT-3.5-turbo / Google Gemini 2.5
- **Database**: Supabase (PostgreSQL)
- **Data**: pandas, openpyxl

## Key Constants

```python
MIN_REVIEWS_PER_BRANCH = 30
MIN_REVIEW_LENGTH = 5
SENTIMENT_THRESHOLD = 0.45  # positive if >= 0.45
LEXICON_HIGH = 0.7          # confident positive
LEXICON_LOW = 0.3           # confident negative
OPENAI_RPM = 3500
GEMINI_RPM = 15
```

## Directory Structure

```
src/
├── analysis/           # Sentiment & keyword modules
│   ├── sentiment/      # Lexicon, BERT, Hybrid analyzers
│   └── keywords/       # MeCab extraction, weighting
├── config/             # Settings, stopwords
├── llm/                # OpenAI & Gemini providers
├── pipeline/           # Batch processing orchestration
├── db/                 # Database connectivity
└── preprocessing/      # Data cleaning

scripts/                # Pipeline execution scripts
web/                    # Flask API + dashboard
data/                   # Input Excel files
output/                 # Generated results
```

## Common Commands

```bash
# Run full pipeline
python scripts/pipeline_v3.py

# Run incremental update
python scripts/pipeline_incremental.py

# Start web dashboard
python web/app.py

# Test LLM provider
python -c "from src.llm import get_provider; p = get_provider(); print(p.model_name)"
```

## Pipeline Overview

1. Load Excel (217K reviews)
2. Clean (remove null/empty)
3. Filter (min 30 reviews/branch)
4. Sentiment analysis (Lexicon + BERT hybrid)
5. Filter positive (score >= 0.45)
6. Keyword extraction (MeCab)
7. Aggregate TOP-10 per branch
8. LLM summarization
9. Export (Excel + Supabase)

## Environment Variables

Required in `.env`:
- `OPENAI_API_KEY` - GPT API key
- `GEMINI_API_KEY` - Google Gemini API key
- `LLM_PROVIDER` - "openai" or "gemini"
- `SUPABASE_URL` - Database URL
- `SUPABASE_KEY` - Service role key

## Status Workflow

Summaries follow: `draft` -> `approved` -> `published`

## Planning with Files Pattern

복잡한 작업 시 컨텍스트 유지를 위한 3-파일 패턴:

| File | Purpose |
|------|---------|
| `docs/task_plan.md` | 작업 계획 & 체크리스트 (결정 전 검토) |
| `docs/findings.md` | 연구 결과 & 코드 분석 저장 |
| `docs/progress.md` | 시도 & 실패 기록 (실수 반복 방지) |

**사용 시점**: 다단계 작업, 리팩토링, 연구 작업
**건너뛸 때**: 단순 쿼리, 빠른 수정
