# app/domain/ — 도메인 로직

## Key Constants

```python
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SIMILARITY_THRESHOLD = 0.50      # 태그 분류 최소 유사도
CONTEXT_WINDOW_SIZE = 50         # 감정 분석 문맥 윈도우 (글자)
```

## 태그 시스템

- 9개 카테고리, 52개 세분화 태그 + "일반" fallback
- 상세 규칙: `analysis/patterns.py` (TAG_REGISTRY, RULE_BASED_TAG_MAPPING)

### 카테고리 (9개 + 일반)

직원친절, 외관, 가격, 청결, 사고 처리, 주유비, 배달/배차, 반납/픽업, 위치/접근성

### "일반" 태그 (fallback)

- id=13853, category_id=8
- 분류 미매핑 리뷰에 자동 부여
- 평점 합산으로 감정 판정

## 감정 분석 규칙

### 판정 방식

규칙 패턴 매칭 + 문맥 분석 (하이브리드)

### 핵심 규칙

- **문맥 윈도우**: 키워드 앞뒤 50자 범위에서 감정 판단
- **이중부정 처리**: `불편함이 없다` → 긍정
- **반전 구문(CONCESSION)**: `~지만`, `~는데` 등 인식 → 뒤쪽 감정 우선
- **동일 카테고리 충돌 해소**: pos+neg 공존 시 다수결, 반전 구문 시 neg 제거

### 패턴 매칭

- 부정 패턴: `불친절`, `비싸`, `냄새`, `아쉬운` 등 (100+개)
- 키워드별 규칙은 `analysis/patterns.py`에 정의

## Directory Structure

| File/Dir | Role |
| -------- | ---- |
| `analysis/patterns.py` | TAG_REGISTRY, 규칙 기반 태그 매핑, 감정 패턴 |
| `analysis/sentiment_core.py` | 핵심 감정 판정 함수 |
| `analysis/sentiment_utils.py` | UnifiedSentimentAnalyzer 통합 분석기 |
| `analysis/tag_embeddings.py` | FastEmbed ONNX 태그 임베딩 |
| `analysis/hybrid_classifier.py` | ABSA + FastEmbed 하이브리드 분류기 |
| `analysis/absa.py` | RuleBasedABSA 절-단위 감정분석 |
| `analysis/extractor.py` | Kiwi 기반 키워드 추출 |
| `pipeline/` | 배치/증분 처리 파이프라인 |
