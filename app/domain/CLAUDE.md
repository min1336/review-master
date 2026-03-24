# app/domain/ — 도메인 로직

## Key Constants

```python
OPENAI_RPM = 3500                # API Rate Limit
EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
SIMILARITY_THRESHOLD = 0.50      # 태그 분류 최소 유사도
CONTEXT_WINDOW_SIZE = 50         # 감정 분석 문맥 윈도우 (글자)
```

## 태그 시스템

- 8개 카테고리, 52개 세분화 태그 + "일반" fallback
- 상세 규칙: `analysis/patterns.py` (RULE_BASED_TAG_MAPPING)

### 카테고리 (7개 + 일반)

직원이 친절함, 사고 처리를 잘해줌, 주유비 부담 없음, 가격이 저렴함, 차량이 청결함, 차량외관이 좋음, 배달 서비스가 우수함

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
| `analysis/patterns.py` | 규칙 기반 태그 매핑, 감정 패턴 |
| `analysis/sentiment.py` | 감정 분석 엔진 |
| `analysis/embeddings.py` | FastEmbed 태그 임베딩 |
| `pipeline/` | 배치/증분 처리 파이프라인 |
