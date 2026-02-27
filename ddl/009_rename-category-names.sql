UPDATE categories SET name = '직원친절',  updated_at = NOW() WHERE name = '직원이 친절함';
UPDATE categories SET name = '외관',      updated_at = NOW() WHERE name = '차량외관이 좋음';
UPDATE categories SET name = '가격',      updated_at = NOW() WHERE name = '가격이 저렴함';
UPDATE categories SET name = '청결',      updated_at = NOW() WHERE name = '차량이 청결함';
UPDATE categories SET name = '사고 처리', updated_at = NOW() WHERE name = '사고 처리를 잘해줌';
UPDATE categories SET name = '주유비',    updated_at = NOW() WHERE name = '주유비 부담 없음';
UPDATE categories SET name = '배달',      updated_at = NOW() WHERE name = '배달 서비스가 우수함';

UPDATE tags SET name = '직원친절'  WHERE name = '직원이 친절함';
UPDATE tags SET name = '사고 처리' WHERE name = '사고 처리를 잘해줌';
UPDATE tags SET name = '주유비'    WHERE name = '주유비 부담 없음';
UPDATE tags SET name = '배달'      WHERE name = '배달 서비스가 우수함';

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
