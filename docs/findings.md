# Findings

연구 결과, API 문서, 코드 분석 등을 저장하는 파일. 컨텍스트 비대화 방지.

---

## Architecture

### Project Structure
```
src/
├── analysis/           # 감성 분석 & 키워드 모듈
│   ├── sentiment/      # Lexicon, BERT, Hybrid 분석기
│   └── keywords/       # MeCab 추출, 가중치 계산
├── config/             # 설정, 불용어
├── llm/                # OpenAI & Gemini 프로바이더
├── pipeline/           # 배치 처리 오케스트레이션
├── db/                 # 데이터베이스 연결
└── preprocessing/      # 데이터 정제
```

### Key Constants
- `MIN_REVIEWS_PER_BRANCH = 30`
- `SENTIMENT_THRESHOLD = 0.45`
- `LEXICON_HIGH = 0.7`, `LEXICON_LOW = 0.3`

---

## Code Analysis

### Sentiment Analysis Flow
1. Lexicon 기반 점수 계산
2. BERT 모델 예측
3. Hybrid: Lexicon 신뢰도 높으면 Lexicon 사용, 아니면 BERT

### Pipeline Flow
1. Excel 로드 (217K 리뷰)
2. 정제 (null/empty 제거)
3. 필터 (지점당 최소 30개 리뷰)
4. 감성 분석
5. 긍정 리뷰 필터 (score >= 0.45)
6. 키워드 추출 (MeCab)
7. TOP-10 집계
8. LLM 요약
9. 내보내기 (Excel + Supabase)

---

## API Documentation

### External APIs
- **OpenAI**: GPT-3.5-turbo (3500 RPM)
- **Gemini**: gemini-2.5 (15 RPM)
- **Supabase**: PostgreSQL via REST API

### Internal Endpoints
See `docs/CARMORE_API.md` for full API documentation.

---

## Research Notes

### 2026-01-16: Planning with Files Pattern
- AI 코딩 도구의 컨텍스트 손실 문제 해결
- 3-파일 패턴: task_plan.md, findings.md, progress.md
- Manus 스타트업에서 검증된 패턴
- 출처: https://aisparkup.com/posts/8340

### 2026-01-16: Awesome Claude Skills
- Claude Skills 커뮤니티 컬렉션 (3,000+ stars)
- 출처: https://github.com/VoltAgent/awesome-claude-skills

**주요 카테고리:**
- 문서: docx, pptx, xlsx, pdf
- 디자인: algorithmic-art, canvas-design, frontend-design
- 개발: web-artifacts-builder, mcp-builder, webapp-testing

**참고할만한 기업 Skills:**
- Vercel: React 패턴, 배포 자동화
- Trail of Bits: 보안 분석 (16개 특화 Skills)
- Sentry: 코드 리뷰, PR 생성
- Cloudflare: Workers, KV 가이드

**프로젝트 관련:**
- 컨텍스트 엔지니어링 패턴
- PostgreSQL 쿼리 실행 (Supabase)
- n8n 워크플로우 자동화

---

## Useful References

- [PIPELINE.md](/PIPELINE.md) - 파이프라인 상세 문서
- [CLAUDE.md](/CLAUDE.md) - 프로젝트 컨텍스트
- [CARMORE_API.md](/docs/CARMORE_API.md) - API 문서
