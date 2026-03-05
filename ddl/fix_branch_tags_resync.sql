-- branch_tags(all) 재집계: review_tag_mappings 기반
-- DDL 009 카테고리 변경 이후 branch_tags가 동기화되지 않은 문제 해결
-- 실행 전 백업 권장: CREATE TABLE branch_tags_backup AS SELECT * FROM branch_tags;

BEGIN;

-- 1. 기존 period_type='all' 레코드 삭제
DELETE FROM branch_tags WHERE period_type = 'all';

-- 2. review_tag_mappings에서 branch별 태그 감정 집계 후 삽입
INSERT INTO branch_tags (branch_id, tag_id, period_type, count, positive_count, negative_count, neutral_count, updated_at)
SELECT
    br.branch_id,
    rtm.tag_id,
    'all' AS period_type,
    COUNT(*) AS count,
    SUM(CASE WHEN rtm.sentiment = 'positive' THEN 1 ELSE 0 END) AS positive_count,
    SUM(CASE WHEN rtm.sentiment = 'negative' THEN 1 ELSE 0 END) AS negative_count,
    SUM(CASE WHEN rtm.sentiment = 'neutral' THEN 1 ELSE 0 END) AS neutral_count,
    NOW() AS updated_at
FROM review_tag_mappings rtm
JOIN branch_reviews br ON br.review_id = rtm.review_id
WHERE br.deleted_at IS NULL
GROUP BY br.branch_id, rtm.tag_id
ON CONFLICT (branch_id, tag_id, period_type)
DO UPDATE SET
    count = EXCLUDED.count,
    positive_count = EXCLUDED.positive_count,
    negative_count = EXCLUDED.negative_count,
    neutral_count = EXCLUDED.neutral_count,
    updated_at = NOW();

COMMIT;
