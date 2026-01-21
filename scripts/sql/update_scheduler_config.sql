-- ============================================================
-- 스케줄러 설정 업데이트 SQL (데이터 분석 기반)
-- Supabase SQL Editor에서 실행
--
-- 분석 결과:
-- - 전체 리뷰: 217,660건, 월평균 2,763건
-- - 지점당 월평균: 3.7건
-- - 성수기 일평균: 113건, 비수기: 80건
--
-- 갱신 기준:
-- - 신규: 30건 이상 리뷰
-- - 갱신: 50건 증가 OR 30% 증가
-- ============================================================

-- 1. 기존 스케줄 비활성화
UPDATE scheduler_config
SET is_enabled = false, updated_at = NOW()
WHERE config_key IN ('peak_season', 'normal_season', 'off_season');

-- 2. 새로운 시즌별 스케줄 삽입/업데이트

-- 성수기 (6~8월): 주 1회 (일요일 새벽 3시)
-- 근거: 일평균 113건, 변화 빠름
INSERT INTO scheduler_config (config_key, cron_expression, is_enabled, description, months)
VALUES ('season_peak', '0 3 * * 0', true, '성수기 - 주 1회 (일요일) 새벽 3시', '6,7,8')
ON CONFLICT (config_key) DO UPDATE SET
    cron_expression = EXCLUDED.cron_expression,
    description = EXCLUDED.description,
    months = EXCLUDED.months,
    is_enabled = true,
    updated_at = NOW();

-- 환절기 (3~5, 9~10월): 격주 (1일, 15일 새벽 3시)
-- 근거: 일평균 95건, 표준 주기
INSERT INTO scheduler_config (config_key, cron_expression, is_enabled, description, months)
VALUES ('season_transition', '0 3 1,15 * *', true, '환절기 - 격주 (1일, 15일) 새벽 3시', '3,4,5,9,10')
ON CONFLICT (config_key) DO UPDATE SET
    cron_expression = EXCLUDED.cron_expression,
    description = EXCLUDED.description,
    months = EXCLUDED.months,
    is_enabled = true,
    updated_at = NOW();

-- 비수기 (11~2월): 월 1회 (1일 새벽 3시)
-- 근거: 일평균 80건, 변화 느림
INSERT INTO scheduler_config (config_key, cron_expression, is_enabled, description, months)
VALUES ('season_off', '0 3 1 * *', true, '비수기 - 월 1회 (1일) 새벽 3시', '1,2,11,12')
ON CONFLICT (config_key) DO UPDATE SET
    cron_expression = EXCLUDED.cron_expression,
    description = EXCLUDED.description,
    months = EXCLUDED.months,
    is_enabled = true,
    updated_at = NOW();

-- 3. 갱신 설정 테이블 (신규)
CREATE TABLE IF NOT EXISTS update_config (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(50) UNIQUE NOT NULL,
    config_value JSONB NOT NULL,
    description TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 갱신 조건 설정
INSERT INTO update_config (config_key, config_value, description)
VALUES (
    'summary_update',
    '{
        "new_summary": {
            "min_reviews": 30,
            "min_review_length": 5
        },
        "update_summary": {
            "min_increase_count": 50,
            "min_increase_rate": 0.30,
            "use_and_condition": false
        },
        "batch_size": 50,
        "rate_limit_delay": 60
    }'::jsonb,
    '요약 생성/갱신 조건 (데이터 분석 기반)'
)
ON CONFLICT (config_key) DO UPDATE SET
    config_value = EXCLUDED.config_value,
    description = EXCLUDED.description,
    updated_at = NOW();

-- 4. 확인 쿼리
SELECT
    config_key,
    cron_expression,
    is_enabled,
    months,
    description
FROM scheduler_config
WHERE is_enabled = true
ORDER BY config_key;

-- 갱신 설정 확인
SELECT * FROM update_config;
