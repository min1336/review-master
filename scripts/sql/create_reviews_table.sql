-- ============================================================
-- 지점별 감정태그 통계 테이블
-- ============================================================
-- 217K 리뷰 전체 저장 대신 지점별 통계만 저장 (용량 99% 절약)

CREATE TABLE IF NOT EXISTS branch_sentiment_stats (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER NOT NULL UNIQUE,
    positive_count INTEGER DEFAULT 0,
    negative_count INTEGER DEFAULT 0,
    neutral_count INTEGER DEFAULT 0,
    total_count INTEGER DEFAULT 0,
    positive_ratio DECIMAL(5,2) DEFAULT 0,  -- 긍정 비율 (%)
    negative_ratio DECIMAL(5,2) DEFAULT 0,  -- 부정 비율 (%)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sentiment_stats_branch ON branch_sentiment_stats(branch_id);

-- ============================================================
-- 최근 리뷰 테이블 (1개월치만 유지)
-- ============================================================
-- 디버깅 및 샘플 확인용, 오래된 데이터는 자동 삭제

CREATE TABLE IF NOT EXISTS recent_reviews (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    sentiment VARCHAR(20) NOT NULL,  -- 'positive', 'negative', 'neutral'
    sentiment_score DECIMAL(5,4),
    review_date TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_recent_reviews_branch ON recent_reviews(branch_id);
CREATE INDEX IF NOT EXISTS idx_recent_reviews_sentiment ON recent_reviews(sentiment);
CREATE INDEX IF NOT EXISTS idx_recent_reviews_created ON recent_reviews(created_at DESC);

-- ============================================================
-- 자동 삭제 함수 (1개월 이전 리뷰 삭제)
-- ============================================================

CREATE OR REPLACE FUNCTION cleanup_old_reviews()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM recent_reviews
    WHERE created_at < NOW() - INTERVAL '1 month';

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- 수동 실행: SELECT cleanup_old_reviews();

-- ============================================================
-- 주기적 정리를 위한 pg_cron 설정 (선택사항)
-- ============================================================
-- Supabase에서 pg_cron 활성화 후 사용 가능
--
-- SELECT cron.schedule(
--     'cleanup-old-reviews',           -- job name
--     '0 3 * * *',                      -- 매일 새벽 3시
--     'SELECT cleanup_old_reviews()'
-- );

-- ============================================================
-- 샘플 쿼리
-- ============================================================

-- 지점별 감정 통계 조회
-- SELECT * FROM branch_sentiment_stats WHERE branch_id = 123;

-- 최근 리뷰 검색 (태그별)
-- SELECT * FROM recent_reviews WHERE sentiment = 'positive' LIMIT 100;

-- 지점별 최근 리뷰
-- SELECT * FROM recent_reviews WHERE branch_id = 123 ORDER BY created_at DESC LIMIT 10;

-- 1개월 이전 리뷰 수동 삭제
-- SELECT cleanup_old_reviews();
