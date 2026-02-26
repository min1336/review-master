-- 기존 tags 테이블에서 category_id가 NULL인 행을 categories 테이블 기준으로 백필
-- TagAggregator 수정 전에 생성된 태그에 대한 일회성 마이그레이션
-- 태그명과 카테고리명이 직접 일치하는 경우 (카테고리 자체가 태그인 경우)

UPDATE tags t
SET category_id = c.id
FROM categories c
WHERE t.category_id IS NULL
  AND t.name = c.name;
