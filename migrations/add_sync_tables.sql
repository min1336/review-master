-- ============================================================
-- 리뷰 동기화를 위한 테이블 마이그레이션
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1. branch_reviews 테이블에 is_new 컬럼 추가
ALTER TABLE branch_reviews
ADD COLUMN IF NOT EXISTS is_new BOOLEAN DEFAULT false;

-- 인덱스 추가 (신규 리뷰 필터링 성능)
CREATE INDEX IF NOT EXISTS idx_branch_reviews_is_new
ON branch_reviews(is_new)
WHERE is_new = true;

-- 2. 동기화 상태 테이블 생성
CREATE TABLE IF NOT EXISTS sync_status (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50) UNIQUE NOT NULL,  -- 'athena_reviews'
    last_sync_at TIMESTAMP WITH TIME ZONE,
    synced_count INTEGER DEFAULT 0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 기본 동기화 상태 레코드 생성
INSERT INTO sync_status (sync_type, last_sync_at, synced_count)
VALUES ('athena_reviews', NULL, 0)
ON CONFLICT (sync_type) DO NOTHING;

-- 업데이트 시 updated_at 자동 갱신 트리거
CREATE OR REPLACE FUNCTION update_sync_status_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_sync_status_updated_at ON sync_status;
CREATE TRIGGER trigger_sync_status_updated_at
    BEFORE UPDATE ON sync_status
    FOR EACH ROW
    EXECUTE FUNCTION update_sync_status_timestamp();

-- ============================================================
-- 확인 쿼리
-- ============================================================
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'branch_reviews';
-- SELECT * FROM sync_status;
