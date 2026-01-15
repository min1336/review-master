-- ============================================================
-- 스케줄러 테이블 생성 SQL
-- Supabase SQL Editor에서 실행
-- ============================================================

-- 1. 스케줄러 설정 테이블
CREATE TABLE IF NOT EXISTS scheduler_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(50) UNIQUE NOT NULL,
    cron_expression VARCHAR(50) NOT NULL,
    is_enabled BOOLEAN DEFAULT true,
    description TEXT,
    months VARCHAR(50),  -- 적용 월 (예: "7,8" 또는 "all")
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 2. 실행 로그 테이블
CREATE TABLE IF NOT EXISTS scheduler_logs (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(50),
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    finished_at TIMESTAMP WITH TIME ZONE,
    branch_count INTEGER DEFAULT 0,
    success_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    status VARCHAR(20) DEFAULT 'running',  -- running, completed, failed
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 3. 인덱스 생성
CREATE INDEX IF NOT EXISTS idx_scheduler_logs_config_key ON scheduler_logs(config_key);
CREATE INDEX IF NOT EXISTS idx_scheduler_logs_started_at ON scheduler_logs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_scheduler_logs_status ON scheduler_logs(status);

-- 4. 분석 결과 기반 기본 스케줄 설정 삽입
-- 성수기 (7~8월): 매일 새벽 3시
INSERT INTO scheduler_config (config_key, cron_expression, is_enabled, description, months)
VALUES ('peak_season', '0 3 * * *', true, '성수기 - 매일 새벽 3시', '7,8')
ON CONFLICT (config_key) DO UPDATE SET
    cron_expression = EXCLUDED.cron_expression,
    description = EXCLUDED.description,
    months = EXCLUDED.months,
    updated_at = NOW();

-- 일반기 (3~6, 9~10월): 주 3회 (월/수/금 새벽 3시)
INSERT INTO scheduler_config (config_key, cron_expression, is_enabled, description, months)
VALUES ('normal_season', '0 3 * * 1,3,5', true, '일반기 - 주 3회 (월/수/금) 새벽 3시', '3,4,5,6,9,10')
ON CONFLICT (config_key) DO UPDATE SET
    cron_expression = EXCLUDED.cron_expression,
    description = EXCLUDED.description,
    months = EXCLUDED.months,
    updated_at = NOW();

-- 비수기 (11~2월): 주 1회 (월요일 새벽 3시)
INSERT INTO scheduler_config (config_key, cron_expression, is_enabled, description, months)
VALUES ('off_season', '0 3 * * 1', true, '비수기 - 주 1회 (월요일) 새벽 3시', '1,2,11,12')
ON CONFLICT (config_key) DO UPDATE SET
    cron_expression = EXCLUDED.cron_expression,
    description = EXCLUDED.description,
    months = EXCLUDED.months,
    updated_at = NOW();

-- 5. updated_at 자동 업데이트 트리거
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_scheduler_config_updated_at ON scheduler_config;
CREATE TRIGGER update_scheduler_config_updated_at
    BEFORE UPDATE ON scheduler_config
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- 6. 확인 쿼리
SELECT * FROM scheduler_config ORDER BY id;
