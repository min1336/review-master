-- 키워드 마이그레이션: keyword_1,2,3 → keywords (JSON 배열)
-- Supabase SQL Editor에서 실행

-- Step 1: keywords 컬럼 추가 (JSONB 타입)
ALTER TABLE branch_summaries 
ADD COLUMN IF NOT EXISTS keywords JSONB DEFAULT '[]'::jsonb;

-- Step 2: 기존 데이터 마이그레이션
UPDATE branch_summaries
SET keywords = (
    SELECT jsonb_agg(kw)
    FROM (
        SELECT unnest(ARRAY[keyword_1, keyword_2, keyword_3]) AS kw
    ) AS keywords_array
    WHERE kw IS NOT NULL AND kw != ''
)
WHERE keyword_1 IS NOT NULL OR keyword_2 IS NOT NULL OR keyword_3 IS NOT NULL;

-- Step 3: 인덱스 생성 (검색 성능 향상)
CREATE INDEX IF NOT EXISTS idx_branch_summaries_keywords 
ON branch_summaries USING GIN (keywords);

-- Step 4: 확인 쿼리
SELECT 
    branch_id,
    branch_name,
    keyword_1,
    keyword_2, 
    keyword_3,
    keywords
FROM branch_summaries
WHERE keywords IS NOT NULL AND jsonb_array_length(keywords) > 0
LIMIT 10;

-- 참고: 기존 keyword_1,2,3 컬럼은 백업용으로 유지
-- 나중에 안전하게 삭제 가능:
-- ALTER TABLE branch_summaries DROP COLUMN keyword_1;
-- ALTER TABLE branch_summaries DROP COLUMN keyword_2;
-- ALTER TABLE branch_summaries DROP COLUMN keyword_3;
