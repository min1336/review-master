-- TAG_REGISTRY 기반 태그 → 카테고리 전체 백필
-- 002에서 t.name = c.name 조건만 사용하여 대부분 매칭 실패했던 문제 수정
-- 각 카테고리의 서브태그 + 카테고리명 자체를 모두 매핑

-- 직원이 친절함 (affiliate)
UPDATE tags t
SET category_id = c.id
FROM categories c
WHERE c.name = '직원이 친절함'
  AND t.name IN ('친절', '안내', '설명', '서비스', '고객응대', '응대속도', '전화응대', '예약', '직원이 친절함')
  AND (t.category_id IS NULL OR t.category_id != c.id);

-- 차량외관이 좋음 (vehicle)
UPDATE tags t
SET category_id = c.id
FROM categories c
WHERE c.name = '차량외관이 좋음'
  AND t.name IN ('외관', '차량외관', '신차', '연식', '성능', '옵션', '차종', '내비게이션', '블랙박스', '차량외관이 좋음')
  AND (t.category_id IS NULL OR t.category_id != c.id);

-- 가격이 저렴함 (affiliate)
UPDATE tags t
SET category_id = c.id
FROM categories c
WHERE c.name = '가격이 저렴함'
  AND t.name IN ('가격', '가성비', '할인', '요금', '추가요금', '정산', '면책금', '보험료', '가격이 저렴함')
  AND (t.category_id IS NULL OR t.category_id != c.id);

-- 차량이 청결함 (vehicle)
UPDATE tags t
SET category_id = c.id
FROM categories c
WHERE c.name = '차량이 청결함'
  AND t.name IN ('청결', '차량청결', '세차', '냄새', '실내', '시트', '트렁크', '차량이 청결함')
  AND (t.category_id IS NULL OR t.category_id != c.id);

-- 사고 처리를 잘해줌 (affiliate)
UPDATE tags t
SET category_id = c.id
FROM categories c
WHERE c.name = '사고 처리를 잘해줌'
  AND t.name IN ('보험/보장', '면책', '사고처리', '수리', '보상', '긴급출동', '대차', '사고 처리를 잘해줌')
  AND (t.category_id IS NULL OR t.category_id != c.id);

-- 주유비 부담 없음 (affiliate)
UPDATE tags t
SET category_id = c.id
FROM categories c
WHERE c.name = '주유비 부담 없음'
  AND t.name IN ('주유', '연비', '충전', '전기차', '만탄', '주유비 부담 없음')
  AND (t.category_id IS NULL OR t.category_id != c.id);

-- 배달 서비스가 우수함 (affiliate)
UPDATE tags t
SET category_id = c.id
FROM categories c
WHERE c.name = '배달 서비스가 우수함'
  AND t.name IN ('딜리버리', '반납/픽업', '배차/시간', '위치/접근성', '탁송', '공항', '대기시간', '주차장', '배달 서비스가 우수함')
  AND (t.category_id IS NULL OR t.category_id != c.id);
