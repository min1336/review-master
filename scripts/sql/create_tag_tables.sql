-- ============================================================
-- 태그 시스템 테이블 생성 스크립트
-- 실행: Supabase SQL Editor에서 실행
-- ============================================================

-- 1. 카테고리 테이블 (태그의 상위 분류)
CREATE TABLE IF NOT EXISTS categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(200),
    display_order INTEGER DEFAULT 0,
    color VARCHAR(7) DEFAULT '#667eea',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 기본 카테고리 삽입
INSERT INTO categories (name, description, display_order, color) VALUES
    ('서비스', '직원 응대, 픽업/반납 등', 1, '#10b981'),
    ('차량', '차량 상태, 청결도 등', 2, '#3b82f6'),
    ('가격', '요금, 가성비 등', 3, '#f59e0b'),
    ('위치', '접근성, 주차 등', 4, '#8b5cf6'),
    ('편의시설', '대기실, 부대시설 등', 5, '#ec4899')
ON CONFLICT (name) DO NOTHING;

-- 2. 태그 테이블 (정제된 키워드)
CREATE TABLE IF NOT EXISTS tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) UNIQUE NOT NULL,
    category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    sentiment VARCHAR(10) DEFAULT 'positive',
    is_active BOOLEAN DEFAULT TRUE,
    usage_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tags_category ON tags(category_id);
CREATE INDEX IF NOT EXISTS idx_tags_sentiment ON tags(sentiment);
CREATE INDEX IF NOT EXISTS idx_tags_active ON tags(is_active) WHERE is_active = TRUE;

-- 3. 키워드-태그 매핑 테이블 (키워드 → 태그)
CREATE TABLE IF NOT EXISTS keyword_tag_mappings (
    id SERIAL PRIMARY KEY,
    keyword VARCHAR(50) NOT NULL,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    is_auto BOOLEAN DEFAULT TRUE,
    confidence DECIMAL(3,2) DEFAULT 1.0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(keyword, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_ktm_keyword ON keyword_tag_mappings(keyword);
CREATE INDEX IF NOT EXISTS idx_ktm_tag ON keyword_tag_mappings(tag_id);

-- 4. 지점별 태그 집계 테이블
CREATE TABLE IF NOT EXISTS branch_tags (
    id SERIAL PRIMARY KEY,
    branch_id INTEGER NOT NULL,
    tag_id INTEGER REFERENCES tags(id) ON DELETE CASCADE,
    period_type VARCHAR(10) NOT NULL DEFAULT 'all',
    count INTEGER DEFAULT 0,
    weighted_score DECIMAL(10,2) DEFAULT 0,
    rank INTEGER,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(branch_id, tag_id, period_type)
);

CREATE INDEX IF NOT EXISTS idx_branch_tags_lookup ON branch_tags(branch_id, period_type);
CREATE INDEX IF NOT EXISTS idx_branch_tags_tag ON branch_tags(tag_id);

-- 5. summaries 테이블 수정 (기간별 요약 지원)
-- period_type 컬럼 추가
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS period_type VARCHAR(10) DEFAULT 'all';
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS period_start DATE;
ALTER TABLE summaries ADD COLUMN IF NOT EXISTS period_end DATE;

-- 기존 UNIQUE 제약 변경 (branch_id, period_type 조합으로)
-- 주의: 기존 데이터가 있으면 먼저 백업 필요
DO $$
BEGIN
    -- 기존 branch_id 단독 unique 제약 삭제 시도
    ALTER TABLE summaries DROP CONSTRAINT IF EXISTS summaries_branch_id_key;
EXCEPTION
    WHEN undefined_object THEN NULL;
END $$;

-- 새 복합 unique 제약 추가
DO $$
BEGIN
    ALTER TABLE summaries ADD CONSTRAINT summaries_branch_period_unique UNIQUE(branch_id, period_type);
EXCEPTION
    WHEN duplicate_table THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_summaries_period ON summaries(period_type);

-- ============================================================
-- 기본 태그 데이터 삽입 (선택사항)
-- ============================================================

-- 서비스 카테고리 태그
INSERT INTO tags (name, category_id, sentiment) VALUES
    ('친절', (SELECT id FROM categories WHERE name = '서비스'), 'positive'),
    ('응대', (SELECT id FROM categories WHERE name = '서비스'), 'positive'),
    ('설명', (SELECT id FROM categories WHERE name = '서비스'), 'positive'),
    ('안내', (SELECT id FROM categories WHERE name = '서비스'), 'positive'),
    ('배려', (SELECT id FROM categories WHERE name = '서비스'), 'positive'),
    ('불친절', (SELECT id FROM categories WHERE name = '서비스'), 'negative')
ON CONFLICT (name) DO NOTHING;

-- 차량 카테고리 태그
INSERT INTO tags (name, category_id, sentiment) VALUES
    ('깨끗', (SELECT id FROM categories WHERE name = '차량'), 'positive'),
    ('청결', (SELECT id FROM categories WHERE name = '차량'), 'positive'),
    ('새차', (SELECT id FROM categories WHERE name = '차량'), 'positive'),
    ('넓은', (SELECT id FROM categories WHERE name = '차량'), 'positive'),
    ('쾌적', (SELECT id FROM categories WHERE name = '차량'), 'positive'),
    ('더러움', (SELECT id FROM categories WHERE name = '차량'), 'negative')
ON CONFLICT (name) DO NOTHING;

-- 가격 카테고리 태그
INSERT INTO tags (name, category_id, sentiment) VALUES
    ('저렴', (SELECT id FROM categories WHERE name = '가격'), 'positive'),
    ('합리적', (SELECT id FROM categories WHERE name = '가격'), 'positive'),
    ('가성비', (SELECT id FROM categories WHERE name = '가격'), 'positive'),
    ('비싼', (SELECT id FROM categories WHERE name = '가격'), 'negative')
ON CONFLICT (name) DO NOTHING;

-- 위치 카테고리 태그
INSERT INTO tags (name, category_id, sentiment) VALUES
    ('접근성', (SELECT id FROM categories WHERE name = '위치'), 'positive'),
    ('편리', (SELECT id FROM categories WHERE name = '위치'), 'positive'),
    ('주차', (SELECT id FROM categories WHERE name = '위치'), 'positive'),
    ('가까운', (SELECT id FROM categories WHERE name = '위치'), 'positive')
ON CONFLICT (name) DO NOTHING;

-- 편의시설 카테고리 태그
INSERT INTO tags (name, category_id, sentiment) VALUES
    ('대기실', (SELECT id FROM categories WHERE name = '편의시설'), 'positive'),
    ('휴게', (SELECT id FROM categories WHERE name = '편의시설'), 'positive'),
    ('편의', (SELECT id FROM categories WHERE name = '편의시설'), 'positive')
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- 기본 키워드-태그 매핑 (동의어 그룹)
-- ============================================================

-- 친절 동의어
INSERT INTO keyword_tag_mappings (keyword, tag_id, is_auto) VALUES
    ('친절한', (SELECT id FROM tags WHERE name = '친절'), TRUE),
    ('친절함', (SELECT id FROM tags WHERE name = '친절'), TRUE),
    ('친절하다', (SELECT id FROM tags WHERE name = '친절'), TRUE),
    ('친절히', (SELECT id FROM tags WHERE name = '친절'), TRUE)
ON CONFLICT (keyword, tag_id) DO NOTHING;

-- 깨끗 동의어
INSERT INTO keyword_tag_mappings (keyword, tag_id, is_auto) VALUES
    ('깨끗한', (SELECT id FROM tags WHERE name = '깨끗'), TRUE),
    ('깨끗함', (SELECT id FROM tags WHERE name = '깨끗'), TRUE),
    ('깔끔', (SELECT id FROM tags WHERE name = '깨끗'), TRUE),
    ('깔끔한', (SELECT id FROM tags WHERE name = '깨끗'), TRUE),
    ('깔끔함', (SELECT id FROM tags WHERE name = '깨끗'), TRUE)
ON CONFLICT (keyword, tag_id) DO NOTHING;

-- 빠른 동의어
INSERT INTO keyword_tag_mappings (keyword, tag_id, is_auto) VALUES
    ('빠른', (SELECT id FROM tags WHERE name = '응대'), TRUE),
    ('빠르다', (SELECT id FROM tags WHERE name = '응대'), TRUE),
    ('신속', (SELECT id FROM tags WHERE name = '응대'), TRUE),
    ('신속한', (SELECT id FROM tags WHERE name = '응대'), TRUE),
    ('신속하다', (SELECT id FROM tags WHERE name = '응대'), TRUE)
ON CONFLICT (keyword, tag_id) DO NOTHING;

-- ============================================================
-- 트리거: updated_at 자동 업데이트
-- ============================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- categories 테이블 트리거
DROP TRIGGER IF EXISTS update_categories_updated_at ON categories;
CREATE TRIGGER update_categories_updated_at
    BEFORE UPDATE ON categories
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- tags 테이블 트리거
DROP TRIGGER IF EXISTS update_tags_updated_at ON tags;
CREATE TRIGGER update_tags_updated_at
    BEFORE UPDATE ON tags
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- branch_tags 테이블 트리거
DROP TRIGGER IF EXISTS update_branch_tags_updated_at ON branch_tags;
CREATE TRIGGER update_branch_tags_updated_at
    BEFORE UPDATE ON branch_tags
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- RLS (Row Level Security) 정책 (선택사항)
-- 필요시 활성화
-- ============================================================

-- ALTER TABLE categories ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE tags ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE keyword_tag_mappings ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE branch_tags ENABLE ROW LEVEL SECURITY;

COMMENT ON TABLE categories IS '태그 카테고리 (서비스, 차량, 가격, 위치, 편의시설)';
COMMENT ON TABLE tags IS '정제된 키워드 태그';
COMMENT ON TABLE keyword_tag_mappings IS '키워드 → 태그 매핑 (동의어 처리)';
COMMENT ON TABLE branch_tags IS '지점별 태그 집계 (기간별)';
