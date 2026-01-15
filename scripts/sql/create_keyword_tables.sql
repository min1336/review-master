-- ============================================================================
-- Review Summary AI - 키워드 가중치 시스템 테이블
-- 실행: Supabase SQL Editor에서 실행
-- ============================================================================

-- 1. 지점별 키워드 테이블 (증분 업데이트용)
CREATE TABLE IF NOT EXISTS branch_keywords (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER NOT NULL,
    keyword VARCHAR(50) NOT NULL,
    raw_count INTEGER DEFAULT 0,              -- 단순 빈도수
    weighted_score DECIMAL(10,2) DEFAULT 0,   -- 가중치 적용 점수
    last_seen_at TIMESTAMP WITH TIME ZONE,    -- 마지막으로 등장한 리뷰 일시
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(branch_id, keyword)
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_branch_keywords_branch_id ON branch_keywords(branch_id);
CREATE INDEX IF NOT EXISTS idx_branch_keywords_score ON branch_keywords(branch_id, weighted_score DESC);

-- 2. 동기화 상태 테이블 (마지막 처리 시점 기록)
CREATE TABLE IF NOT EXISTS sync_status (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER UNIQUE,                 -- NULL이면 전체 동기화 상태
    last_review_id INTEGER,                   -- 마지막 처리 리뷰 ID
    last_review_date TIMESTAMP WITH TIME ZONE, -- 마지막 처리 리뷰 일시
    last_sync_at TIMESTAMP WITH TIME ZONE,    -- 마지막 동기화 시각
    review_count INTEGER DEFAULT 0,           -- 처리된 리뷰 수
    keyword_count INTEGER DEFAULT 0,          -- 추출된 키워드 수
    next_summary_update_at TIMESTAMP WITH TIME ZONE, -- 요약 재생성 예정 시점
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. 키워드 변경 이력 테이블 (선택적 - 변화 추적용)
CREATE TABLE IF NOT EXISTS keyword_history (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER NOT NULL,
    snapshot_date DATE NOT NULL,
    top_keywords JSONB,                       -- [{keyword, score, rank}]
    summary_regenerated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_keyword_history_branch_date
    ON keyword_history(branch_id, snapshot_date DESC);

-- 4. updated_at 자동 업데이트 트리거
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- branch_keywords 트리거
DROP TRIGGER IF EXISTS update_branch_keywords_updated_at ON branch_keywords;
CREATE TRIGGER update_branch_keywords_updated_at
    BEFORE UPDATE ON branch_keywords
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- sync_status 트리거
DROP TRIGGER IF EXISTS update_sync_status_updated_at ON sync_status;
CREATE TRIGGER update_sync_status_updated_at
    BEFORE UPDATE ON sync_status
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 5. 지점별 TOP N 키워드 조회 함수
CREATE OR REPLACE FUNCTION get_top_keywords(p_branch_id INTEGER, p_limit INTEGER DEFAULT 10)
RETURNS TABLE(keyword VARCHAR, weighted_score DECIMAL, raw_count INTEGER, rank INTEGER) AS $$
BEGIN
    RETURN QUERY
    SELECT
        bk.keyword,
        bk.weighted_score,
        bk.raw_count,
        ROW_NUMBER() OVER (ORDER BY bk.weighted_score DESC)::INTEGER as rank
    FROM branch_keywords bk
    WHERE bk.branch_id = p_branch_id
    ORDER BY bk.weighted_score DESC
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- 6. 시간 감쇠 적용 함수 (배치로 전체 키워드 점수 감소)
CREATE OR REPLACE FUNCTION apply_time_decay(p_decay_factor DECIMAL DEFAULT 0.95)
RETURNS INTEGER AS $$
DECLARE
    updated_count INTEGER;
BEGIN
    UPDATE branch_keywords
    SET weighted_score = weighted_score * p_decay_factor
    WHERE weighted_score > 0.01;  -- 너무 작은 값은 무시

    GET DIAGNOSTICS updated_count = ROW_COUNT;
    RETURN updated_count;
END;
$$ LANGUAGE plpgsql;

-- 7. 오래된 키워드 정리 함수 (6개월 이상 미등장)
CREATE OR REPLACE FUNCTION cleanup_stale_keywords(p_days INTEGER DEFAULT 180)
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM branch_keywords
    WHERE last_seen_at < NOW() - (p_days || ' days')::INTERVAL
      AND weighted_score < 1.0;  -- 점수가 낮은 것만 삭제

    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- 초기 데이터 (선택적)
-- ============================================================================

-- 전체 동기화 상태 초기화
INSERT INTO sync_status (branch_id, last_sync_at, review_count)
VALUES (NULL, NULL, 0)
ON CONFLICT DO NOTHING;

-- ============================================================================
-- 확인 쿼리
-- ============================================================================
-- SELECT * FROM branch_keywords WHERE branch_id = 1234 ORDER BY weighted_score DESC LIMIT 10;
-- SELECT * FROM get_top_keywords(1234, 10);
-- SELECT apply_time_decay(0.95);
-- SELECT cleanup_stale_keywords(180);
