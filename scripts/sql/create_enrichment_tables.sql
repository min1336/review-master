-- ============================================================
-- Carmore API 연동을 위한 Enrichment 테이블
-- ============================================================

-- 제휴사(업체) 정보 캐시 테이블
CREATE TABLE IF NOT EXISTS affiliates (
    id SERIAL PRIMARY KEY,
    affiliate_index INTEGER UNIQUE NOT NULL,  -- Carmore API의 지점 인덱스
    name VARCHAR(200),                        -- 업체명
    location_type VARCHAR(50) DEFAULT 'PARTNERS',  -- PARTNERS, JEJU, GLOBAL
    address TEXT,                             -- 주소
    phone VARCHAR(50),                        -- 연락처
    latitude DECIMAL(10, 7),                  -- 위도
    longitude DECIMAL(10, 7),                 -- 경도
    is_active BOOLEAN DEFAULT TRUE,           -- 활성 상태
    raw_data JSONB,                           -- API 원본 응답 저장
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_affiliates_affiliate_index ON affiliates(affiliate_index);
CREATE INDEX IF NOT EXISTS idx_affiliates_location_type ON affiliates(location_type);
CREATE INDEX IF NOT EXISTS idx_affiliates_is_active ON affiliates(is_active);

-- 차종 정보 캐시 테이블
CREATE TABLE IF NOT EXISTS car_models (
    id SERIAL PRIMARY KEY,
    model_id VARCHAR(100) UNIQUE NOT NULL,    -- 차종 고유 ID
    name VARCHAR(200),                        -- 차종명 (한글)
    name_en VARCHAR(200),                     -- 차종명 (영문)
    category VARCHAR(50),                     -- 카테고리 (소형, 중형, 대형, SUV 등)
    brand VARCHAR(100),                       -- 제조사/브랜드
    seats INTEGER,                            -- 좌석 수
    fuel_type VARCHAR(50),                    -- 연료 타입 (가솔린, 디젤, 전기 등)
    transmission VARCHAR(50),                 -- 변속기 (자동, 수동)
    image_url TEXT,                           -- 차량 이미지 URL
    raw_data JSONB,                           -- API 원본 응답 저장
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_car_models_model_id ON car_models(model_id);
CREATE INDEX IF NOT EXISTS idx_car_models_category ON car_models(category);
CREATE INDEX IF NOT EXISTS idx_car_models_brand ON car_models(brand);

-- API 동기화 이력 테이블
CREATE TABLE IF NOT EXISTS api_sync_logs (
    id SERIAL PRIMARY KEY,
    sync_type VARCHAR(50) NOT NULL,           -- 동기화 타입 (affiliates, car_models, reviews)
    status VARCHAR(20) DEFAULT 'running',     -- running, completed, failed
    total_count INTEGER DEFAULT 0,            -- 전체 항목 수
    success_count INTEGER DEFAULT 0,          -- 성공 항목 수
    error_message TEXT,                       -- 에러 메시지
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE
);

-- 인덱스
CREATE INDEX IF NOT EXISTS idx_api_sync_logs_sync_type ON api_sync_logs(sync_type);
CREATE INDEX IF NOT EXISTS idx_api_sync_logs_status ON api_sync_logs(status);
CREATE INDEX IF NOT EXISTS idx_api_sync_logs_started_at ON api_sync_logs(started_at DESC);

-- updated_at 자동 갱신 트리거 함수
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- affiliates 테이블 트리거
DROP TRIGGER IF EXISTS update_affiliates_updated_at ON affiliates;
CREATE TRIGGER update_affiliates_updated_at
    BEFORE UPDATE ON affiliates
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- car_models 테이블 트리거
DROP TRIGGER IF EXISTS update_car_models_updated_at ON car_models;
CREATE TRIGGER update_car_models_updated_at
    BEFORE UPDATE ON car_models
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- 코멘트
-- ============================================================

COMMENT ON TABLE affiliates IS 'Carmore API에서 조회한 제휴사(렌터카 업체) 정보 캐시';
COMMENT ON TABLE car_models IS 'Carmore API에서 조회한 차종 정보 캐시';
COMMENT ON TABLE api_sync_logs IS 'API 동기화 작업 이력';

COMMENT ON COLUMN affiliates.affiliate_index IS 'Carmore API의 affiliateBranchIndex';
COMMENT ON COLUMN affiliates.raw_data IS 'API 원본 응답 JSON (향후 필드 추가 대비)';
COMMENT ON COLUMN car_models.model_id IS 'Carmore API의 차종 고유 식별자';
COMMENT ON COLUMN car_models.raw_data IS 'API 원본 응답 JSON (향후 필드 추가 대비)';
