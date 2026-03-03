-- 009b: 구버전 카테고리/태그 병합 (009 보완)
-- 009가 unique 제약으로 실패하는 4개 태그(직원친절, 사고 처리, 주유비, 배달)를 안전하게 병합
-- 이름 기반 쿼리 — 어떤 DB에서든 실행 가능 (ID 무관)
-- 멱등성: 이미 적용된 환경에서 재실행해도 안전

BEGIN;

-- ============================================================
-- Step 1: categories 이름 변경 (이미 적용됐으면 0 rows)
-- ============================================================
UPDATE categories SET name = '직원친절',  updated_at = NOW() WHERE name = '직원이 친절함';
UPDATE categories SET name = '외관',      updated_at = NOW() WHERE name = '차량외관이 좋음';
UPDATE categories SET name = '가격',      updated_at = NOW() WHERE name = '가격이 저렴함';
UPDATE categories SET name = '청결',      updated_at = NOW() WHERE name = '차량이 청결함';
UPDATE categories SET name = '사고 처리', updated_at = NOW() WHERE name = '사고 처리를 잘해줌';
UPDATE categories SET name = '주유비',    updated_at = NOW() WHERE name = '주유비 부담 없음';
UPDATE categories SET name = '배달',      updated_at = NOW() WHERE name = '배달 서비스가 우수함';

-- ============================================================
-- Step 2: 신규 태그에 category_id 연결 (NULL인 경우만)
-- ============================================================
UPDATE tags SET category_id = (SELECT id FROM categories WHERE name = '직원친절')
WHERE name = '직원친절' AND category_id IS NULL;

UPDATE tags SET category_id = (SELECT id FROM categories WHERE name = '사고 처리')
WHERE name = '사고 처리' AND category_id IS NULL;

UPDATE tags SET category_id = (SELECT id FROM categories WHERE name = '주유비')
WHERE name = '주유비' AND category_id IS NULL;

UPDATE tags SET category_id = (SELECT id FROM categories WHERE name = '배달')
WHERE name = '배달' AND category_id IS NULL;

-- ============================================================
-- Step 3: 직원이 친절함 → 직원친절 병합
-- ============================================================
DELETE FROM review_tag_mappings rtm
WHERE rtm.tag_id = (SELECT id FROM tags WHERE name = '직원이 친절함' LIMIT 1)
  AND EXISTS (
    SELECT 1 FROM review_tag_mappings rtm2
    WHERE rtm2.review_id = rtm.review_id
      AND rtm2.tag_id = (SELECT id FROM tags WHERE name = '직원친절' LIMIT 1)
      AND rtm2.sentiment = rtm.sentiment
  );
UPDATE review_tag_mappings
SET tag_id = (SELECT id FROM tags WHERE name = '직원친절' LIMIT 1)
WHERE tag_id = (SELECT id FROM tags WHERE name = '직원이 친절함' LIMIT 1);
DELETE FROM keyword_mappings WHERE tag_id = (SELECT id FROM tags WHERE name = '직원이 친절함' LIMIT 1);
DELETE FROM monthly_car_model_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '직원이 친절함' LIMIT 1);
DELETE FROM monthly_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '직원이 친절함' LIMIT 1);
DELETE FROM branch_tags WHERE tag_id = (SELECT id FROM tags WHERE name = '직원이 친절함' LIMIT 1);
DELETE FROM tags WHERE name = '직원이 친절함';

-- ============================================================
-- Step 4: 사고 처리를 잘해줌 → 사고 처리 병합
-- ============================================================
DELETE FROM review_tag_mappings rtm
WHERE rtm.tag_id = (SELECT id FROM tags WHERE name = '사고 처리를 잘해줌' LIMIT 1)
  AND EXISTS (
    SELECT 1 FROM review_tag_mappings rtm2
    WHERE rtm2.review_id = rtm.review_id
      AND rtm2.tag_id = (SELECT id FROM tags WHERE name = '사고 처리' LIMIT 1)
      AND rtm2.sentiment = rtm.sentiment
  );
UPDATE review_tag_mappings
SET tag_id = (SELECT id FROM tags WHERE name = '사고 처리' LIMIT 1)
WHERE tag_id = (SELECT id FROM tags WHERE name = '사고 처리를 잘해줌' LIMIT 1);
DELETE FROM keyword_mappings WHERE tag_id = (SELECT id FROM tags WHERE name = '사고 처리를 잘해줌' LIMIT 1);
DELETE FROM monthly_car_model_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '사고 처리를 잘해줌' LIMIT 1);
DELETE FROM monthly_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '사고 처리를 잘해줌' LIMIT 1);
DELETE FROM branch_tags WHERE tag_id = (SELECT id FROM tags WHERE name = '사고 처리를 잘해줌' LIMIT 1);
DELETE FROM tags WHERE name = '사고 처리를 잘해줌';

-- ============================================================
-- Step 5: 주유비 부담 없음 → 주유비 병합
-- ============================================================
DELETE FROM review_tag_mappings rtm
WHERE rtm.tag_id = (SELECT id FROM tags WHERE name = '주유비 부담 없음' LIMIT 1)
  AND EXISTS (
    SELECT 1 FROM review_tag_mappings rtm2
    WHERE rtm2.review_id = rtm.review_id
      AND rtm2.tag_id = (SELECT id FROM tags WHERE name = '주유비' LIMIT 1)
      AND rtm2.sentiment = rtm.sentiment
  );
UPDATE review_tag_mappings
SET tag_id = (SELECT id FROM tags WHERE name = '주유비' LIMIT 1)
WHERE tag_id = (SELECT id FROM tags WHERE name = '주유비 부담 없음' LIMIT 1);
DELETE FROM keyword_mappings WHERE tag_id = (SELECT id FROM tags WHERE name = '주유비 부담 없음' LIMIT 1);
DELETE FROM monthly_car_model_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '주유비 부담 없음' LIMIT 1);
DELETE FROM monthly_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '주유비 부담 없음' LIMIT 1);
DELETE FROM branch_tags WHERE tag_id = (SELECT id FROM tags WHERE name = '주유비 부담 없음' LIMIT 1);
DELETE FROM tags WHERE name = '주유비 부담 없음';

-- ============================================================
-- Step 6: 배달 서비스가 우수함 → 배달 병합
-- ============================================================
DELETE FROM review_tag_mappings rtm
WHERE rtm.tag_id = (SELECT id FROM tags WHERE name = '배달 서비스가 우수함' LIMIT 1)
  AND EXISTS (
    SELECT 1 FROM review_tag_mappings rtm2
    WHERE rtm2.review_id = rtm.review_id
      AND rtm2.tag_id = (SELECT id FROM tags WHERE name = '배달' LIMIT 1)
      AND rtm2.sentiment = rtm.sentiment
  );
UPDATE review_tag_mappings
SET tag_id = (SELECT id FROM tags WHERE name = '배달' LIMIT 1)
WHERE tag_id = (SELECT id FROM tags WHERE name = '배달 서비스가 우수함' LIMIT 1);
DELETE FROM keyword_mappings WHERE tag_id = (SELECT id FROM tags WHERE name = '배달 서비스가 우수함' LIMIT 1);
DELETE FROM monthly_car_model_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '배달 서비스가 우수함' LIMIT 1);
DELETE FROM monthly_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '배달 서비스가 우수함' LIMIT 1);
DELETE FROM branch_tags WHERE tag_id = (SELECT id FROM tags WHERE name = '배달 서비스가 우수함' LIMIT 1);
DELETE FROM tags WHERE name = '배달 서비스가 우수함';

-- ============================================================
-- Step 7: 차량외관이 좋음 → 외관 병합 (009 원본과 동일, 멱등)
-- ============================================================
DELETE FROM review_tag_mappings rtm
WHERE rtm.tag_id = (SELECT id FROM tags WHERE name = '차량외관이 좋음' LIMIT 1)
  AND EXISTS (
    SELECT 1 FROM review_tag_mappings rtm2
    WHERE rtm2.review_id = rtm.review_id
      AND rtm2.tag_id = (SELECT id FROM tags WHERE name = '외관' LIMIT 1)
      AND rtm2.sentiment = rtm.sentiment
  );
UPDATE review_tag_mappings
SET tag_id = (SELECT id FROM tags WHERE name = '외관' LIMIT 1)
WHERE tag_id = (SELECT id FROM tags WHERE name = '차량외관이 좋음' LIMIT 1);
DELETE FROM keyword_mappings WHERE tag_id = (SELECT id FROM tags WHERE name = '차량외관이 좋음' LIMIT 1);
DELETE FROM monthly_car_model_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '차량외관이 좋음' LIMIT 1);
DELETE FROM monthly_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '차량외관이 좋음' LIMIT 1);
DELETE FROM branch_tags WHERE tag_id = (SELECT id FROM tags WHERE name = '차량외관이 좋음' LIMIT 1);
DELETE FROM tags WHERE name = '차량외관이 좋음';

-- ============================================================
-- Step 8: 가격이 저렴함 → 가격 병합 (009 원본과 동일, 멱등)
-- ============================================================
DELETE FROM review_tag_mappings rtm
WHERE rtm.tag_id = (SELECT id FROM tags WHERE name = '가격이 저렴함' LIMIT 1)
  AND EXISTS (
    SELECT 1 FROM review_tag_mappings rtm2
    WHERE rtm2.review_id = rtm.review_id
      AND rtm2.tag_id = (SELECT id FROM tags WHERE name = '가격' LIMIT 1)
      AND rtm2.sentiment = rtm.sentiment
  );
UPDATE review_tag_mappings
SET tag_id = (SELECT id FROM tags WHERE name = '가격' LIMIT 1)
WHERE tag_id = (SELECT id FROM tags WHERE name = '가격이 저렴함' LIMIT 1);
DELETE FROM keyword_mappings WHERE tag_id = (SELECT id FROM tags WHERE name = '가격이 저렴함' LIMIT 1);
DELETE FROM monthly_car_model_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '가격이 저렴함' LIMIT 1);
DELETE FROM monthly_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '가격이 저렴함' LIMIT 1);
DELETE FROM branch_tags WHERE tag_id = (SELECT id FROM tags WHERE name = '가격이 저렴함' LIMIT 1);
DELETE FROM tags WHERE name = '가격이 저렴함';

-- ============================================================
-- Step 9: 차량이 청결함 → 청결 병합 (009 원본과 동일, 멱등)
-- ============================================================
DELETE FROM review_tag_mappings rtm
WHERE rtm.tag_id = (SELECT id FROM tags WHERE name = '차량이 청결함' LIMIT 1)
  AND EXISTS (
    SELECT 1 FROM review_tag_mappings rtm2
    WHERE rtm2.review_id = rtm.review_id
      AND rtm2.tag_id = (SELECT id FROM tags WHERE name = '청결' LIMIT 1)
      AND rtm2.sentiment = rtm.sentiment
  );
UPDATE review_tag_mappings
SET tag_id = (SELECT id FROM tags WHERE name = '청결' LIMIT 1)
WHERE tag_id = (SELECT id FROM tags WHERE name = '차량이 청결함' LIMIT 1);
DELETE FROM keyword_mappings WHERE tag_id = (SELECT id FROM tags WHERE name = '차량이 청결함' LIMIT 1);
DELETE FROM monthly_car_model_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '차량이 청결함' LIMIT 1);
DELETE FROM monthly_tag_stats WHERE tag_id = (SELECT id FROM tags WHERE name = '차량이 청결함' LIMIT 1);
DELETE FROM branch_tags WHERE tag_id = (SELECT id FROM tags WHERE name = '차량이 청결함' LIMIT 1);
DELETE FROM tags WHERE name = '차량이 청결함';

-- ============================================================
-- Step 10: JSONB 텍스트 치환 (branch_reports, branch_summaries)
-- ============================================================
UPDATE branch_reports
SET report_data = replace(replace(replace(replace(replace(replace(replace(
    report_data::text,
    '직원이 친절함', '직원친절'),
    '차량외관이 좋음', '외관'),
    '가격이 저렴함', '가격'),
    '차량이 청결함', '청결'),
    '사고 처리를 잘해줌', '사고 처리'),
    '주유비 부담 없음', '주유비'),
    '배달 서비스가 우수함', '배달')::jsonb,
    updated_at = NOW()
WHERE report_data::text ~ '직원이 친절함|차량외관이 좋음|가격이 저렴함|차량이 청결함|사고 처리를 잘해줌|주유비 부담 없음|배달 서비스가 우수함';

UPDATE branch_summaries
SET ai_report_data = replace(replace(replace(replace(replace(replace(replace(
    ai_report_data::text,
    '직원이 친절함', '직원친절'),
    '차량외관이 좋음', '외관'),
    '가격이 저렴함', '가격'),
    '차량이 청결함', '청결'),
    '사고 처리를 잘해줌', '사고 처리'),
    '주유비 부담 없음', '주유비'),
    '배달 서비스가 우수함', '배달')::jsonb,
    updated_at = NOW()
WHERE ai_report_data IS NOT NULL
  AND ai_report_data::text ~ '직원이 친절함|차량외관이 좋음|가격이 저렴함|차량이 청결함|사고 처리를 잘해줌|주유비 부담 없음|배달 서비스가 우수함';

COMMIT;
