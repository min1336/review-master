-- AI 리포트 태그 통계 함수 및 기반 데이터 보정
-- categories 테이블 채움 → tags.category_id 백필 → getTagStatsByPeriod RPC 함수 생성

BEGIN;

-- 1. categories 테이블에 7개 카테고리 삽입
INSERT INTO categories (id, name, description, color, display_order, is_active)
VALUES
    (1, '직원이 친절함',      '직원 친절, 응대, 서비스 관련',       '#10b981', 1, true),
    (2, '차량외관이 좋음',    '차량 외관, 성능, 옵션 관련',         '#3b82f6', 2, true),
    (3, '가격이 저렴함',      '가격, 가성비, 요금 관련',            '#8b5cf6', 3, true),
    (4, '차량이 청결함',      '차량 청결, 세차, 실내 관련',         '#f59e0b', 4, true),
    (5, '사고 처리를 잘해줌', '보험, 사고처리, 긴급출동 관련',      '#ef4444', 5, true),
    (6, '주유비 부담 없음',   '주유, 연비, 충전 관련',              '#06b6d4', 6, true),
    (7, '배달 서비스가 우수함','딜리버리, 반납, 위치 관련',          '#f97316', 7, true)
ON CONFLICT (id) DO UPDATE SET color = EXCLUDED.color;

-- 시퀀스 보정 (다음 INSERT 시 ID 충돌 방지)
SELECT setval(pg_get_serial_sequence('categories', 'id'), GREATEST(
    (SELECT MAX(id) FROM categories), 7
));

-- 2. tags.category_id 백필 (TAG_REGISTRY 기반, DDL 006 패턴)
-- 직원친절 (affiliate)
UPDATE tags SET category_id = 1
WHERE name IN ('친절','안내','설명','서비스','고객응대','응대속도','전화응대','예약','직원이 친절함','직원친절')
  AND (category_id IS NULL OR category_id != 1);

-- 외관 (vehicle)
UPDATE tags SET category_id = 2
WHERE name IN ('외관','차량외관','신차','연식','성능','옵션','차종','내비게이션','블랙박스','차량외관이 좋음')
  AND (category_id IS NULL OR category_id != 2);

-- 가격 (affiliate)
UPDATE tags SET category_id = 3
WHERE name IN ('가격','가성비','할인','요금','추가요금','정산','면책금','보험료','가격이 저렴함')
  AND (category_id IS NULL OR category_id != 3);

-- 청결 (vehicle)
UPDATE tags SET category_id = 4
WHERE name IN ('청결','차량청결','세차','냄새','실내','시트','트렁크','차량이 청결함')
  AND (category_id IS NULL OR category_id != 4);

-- 사고 처리 (affiliate)
UPDATE tags SET category_id = 5
WHERE name IN ('보험/보장','면책','사고처리','수리','보상','긴급출동','대차','사고 처리를 잘해줌','사고 처리')
  AND (category_id IS NULL OR category_id != 5);

-- 주유비 (affiliate)
UPDATE tags SET category_id = 6
WHERE name IN ('주유','연비','충전','전기차','만탄','주유비 부담 없음','주유비')
  AND (category_id IS NULL OR category_id != 6);

-- 배달 (affiliate)
UPDATE tags SET category_id = 7
WHERE name IN ('딜리버리','반납/픽업','배차/시간','위치/접근성','탁송','공항','대기시간','주차장','배달 서비스가 우수함','배달')
  AND (category_id IS NULL OR category_id != 7);

-- 3. getTagStatsByPeriod RPC 함수 생성
-- review_tag_mappings + branch_reviews + tags + categories 조인으로
-- 지점별·기간별 태그 감정 통계 반환
CREATE OR REPLACE FUNCTION "getTagStatsByPeriod"(
    p_branch_id INTEGER,
    p_start_date TEXT,
    p_end_date TEXT
)
RETURNS TABLE(
    "tagName"       VARCHAR,
    "categoryName"  VARCHAR,
    "positiveCount" BIGINT,
    "negativeCount" BIGINT,
    "neutralCount"  BIGINT,
    "totalCount"    BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.name                                                          AS "tagName",
        COALESCE(c.name, '')::VARCHAR                                   AS "categoryName",
        COUNT(*) FILTER (WHERE rtm.sentiment = 'positive')              AS "positiveCount",
        COUNT(*) FILTER (WHERE rtm.sentiment = 'negative')              AS "negativeCount",
        COUNT(*) FILTER (WHERE rtm.sentiment IN ('neutral','mixed'))    AS "neutralCount",
        COUNT(*)                                                        AS "totalCount"
    FROM review_tag_mappings rtm
    JOIN branch_reviews br ON rtm.review_id = br.review_id
    JOIN tags t ON rtm.tag_id = t.id
    LEFT JOIN categories c ON t.category_id = c.id
    WHERE br.branch_id = p_branch_id
      AND br.review_date >= p_start_date::TIMESTAMP
      AND br.review_date < p_end_date::TIMESTAMP
    GROUP BY t.name, c.name
    HAVING COUNT(*) > 0
    ORDER BY COUNT(*) DESC;
END;
$$ LANGUAGE plpgsql STABLE;

COMMIT;
