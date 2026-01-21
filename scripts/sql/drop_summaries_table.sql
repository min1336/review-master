-- ============================================================
-- summaries 테이블 삭제
--
-- 주의: 이 스크립트를 실행하면 summaries 테이블이 완전히 삭제됩니다.
-- branch_summaries 테이블로 마이그레이션이 완료된 후 실행하세요.
--
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1. summaries 테이블에 걸린 인덱스 먼저 삭제
DROP INDEX IF EXISTS idx_summaries_branch_id;
DROP INDEX IF EXISTS idx_summaries_status;

-- 2. summaries 테이블 삭제
DROP TABLE IF EXISTS summaries;

-- 3. 삭제 확인
-- 아래 쿼리로 테이블이 삭제되었는지 확인
-- SELECT table_name FROM information_schema.tables
-- WHERE table_schema = 'public' AND table_name = 'summaries';
