-- ============================================================
-- Review Summary AI - 데이터베이스 인덱스 생성
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1. branch_summaries 테이블 인덱스
-- branch_id는 이미 UNIQUE일 가능성 높음, 확인 후 생성
CREATE INDEX IF NOT EXISTS idx_branch_summaries_status
ON branch_summaries(status);

CREATE INDEX IF NOT EXISTS idx_branch_summaries_updated_at
ON branch_summaries(updated_at DESC);

-- 복합 인덱스: 상태별 최신순 조회
CREATE INDEX IF NOT EXISTS idx_branch_summaries_status_updated
ON branch_summaries(status, updated_at DESC);


-- 2. branch_tags 테이블 인덱스
CREATE INDEX IF NOT EXISTS idx_branch_tags_branch_id
ON branch_tags(branch_id);

CREATE INDEX IF NOT EXISTS idx_branch_tags_tag_id
ON branch_tags(tag_id);

-- 복합 인덱스: 지점+기간별 조회 (가장 자주 사용)
CREATE INDEX IF NOT EXISTS idx_branch_tags_branch_period
ON branch_tags(branch_id, period_type);


-- 3. tags 테이블 인덱스
CREATE INDEX IF NOT EXISTS idx_tags_group_name
ON tags(group_name);

CREATE INDEX IF NOT EXISTS idx_tags_name
ON tags(name);

CREATE INDEX IF NOT EXISTS idx_tags_sentiment
ON tags(sentiment);


-- 4. keyword_tag_mappings 테이블 인덱스
CREATE INDEX IF NOT EXISTS idx_keyword_mappings_keyword
ON keyword_tag_mappings(keyword);

CREATE INDEX IF NOT EXISTS idx_keyword_mappings_tag_id
ON keyword_tag_mappings(tag_id);


-- 5. affiliates 테이블 인덱스
CREATE INDEX IF NOT EXISTS idx_affiliates_name
ON affiliates(name);

-- 텍스트 검색용 (ILIKE 쿼리 최적화)
CREATE INDEX IF NOT EXISTS idx_affiliates_name_trgm
ON affiliates USING gin(name gin_trgm_ops);


-- 6. branches 테이블 인덱스
CREATE INDEX IF NOT EXISTS idx_branches_branch_id
ON branches(branch_id);


-- ============================================================
-- 인덱스 확인 쿼리
-- ============================================================
-- SELECT indexname, indexdef
-- FROM pg_indexes
-- WHERE schemaname = 'public'
-- ORDER BY tablename, indexname;
