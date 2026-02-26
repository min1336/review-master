create table public.branches
(
    id         serial
        primary key,
    branch_id  integer not null
        unique,
    name       varchar(100),
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

alter table public.branches
    owner to postgres;

grant select, update, usage on sequence public.branches_id_seq to anon;

grant select, update, usage on sequence public.branches_id_seq to authenticated;

grant select, update, usage on sequence public.branches_id_seq to service_role;

create index idx_branches_name
    on public.branches (name);

grant delete, insert, references, select, trigger, truncate, update on public.branches to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branches to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branches to service_role;

create table public.branch_keywords
(
    id             serial
        primary key,
    branch_id      integer     not null,
    keyword        varchar(50) not null,
    raw_count      integer                  default 0,
    weighted_score numeric(10, 2)           default 0,
    last_seen_at   timestamp with time zone,
    created_at     timestamp with time zone default now(),
    updated_at     timestamp with time zone default now(),
    count          integer                  default 0,
    unique (branch_id, keyword)
)
    with (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);

alter table public.branch_keywords
    owner to postgres;

grant select, update, usage on sequence public.branch_keywords_id_seq to anon;

grant select, update, usage on sequence public.branch_keywords_id_seq to authenticated;

grant select, update, usage on sequence public.branch_keywords_id_seq to service_role;

create index idx_keywords_branch
    on public.branch_keywords (branch_id);

create index idx_keywords_keyword
    on public.branch_keywords (keyword);

grant delete, insert, references, select, trigger, truncate, update on public.branch_keywords to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_keywords to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_keywords to service_role;

create table public.affiliates
(
    id              serial
        primary key,
    affiliate_index integer not null
        unique,
    name            varchar(200),
    location_type   varchar(50)              default 'PARTNERS'::character varying,
    address         text,
    phone           varchar(50),
    latitude        numeric(10, 7),
    longitude       numeric(10, 7),
    is_active       boolean                  default true,
    raw_data        jsonb,
    created_at      timestamp with time zone default now(),
    updated_at      timestamp with time zone default now()
);

alter table public.affiliates
    owner to postgres;

grant select, update, usage on sequence public.affiliates_id_seq to anon;

grant select, update, usage on sequence public.affiliates_id_seq to authenticated;

grant select, update, usage on sequence public.affiliates_id_seq to service_role;

create index idx_affiliates_affiliate_index
    on public.affiliates (affiliate_index);

create index idx_affiliates_location
    on public.affiliates (location_type);

grant delete, insert, references, select, trigger, truncate, update on public.affiliates to anon;

grant delete, insert, references, select, trigger, truncate, update on public.affiliates to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.affiliates to service_role;

create table public.branch_summaries
(
    id                     serial
        primary key,
    branch_id              integer not null
        unique,
    branch_name            varchar(100),
    region                 varchar(100),
    review_count           integer                  default 0,
    avg_rating             numeric(3, 2),
    keyword_1              varchar(50),
    keyword_2              varchar(50),
    keyword_3              varchar(50),
    summary_1m             text,
    summary_3m             text,
    summary_6m             text,
    summary_1y             text,
    summary_all            text,
    status                 varchar(20)              default 'draft'::character varying,
    created_at             timestamp with time zone default now(),
    updated_at             timestamp with time zone default now(),
    keywords               jsonb                    default '[]'::jsonb,
    ai_report_data         jsonb,
    ai_report_generated_at timestamp with time zone,
    pending_summaries      jsonb                    default '{}'::jsonb
);

comment on table public.branch_summaries is '지점별 통합 요약 테이블 - 모든 기간별 요약을 단일 행에 저장';

comment on column public.branch_summaries.branch_id is '지점 고유 번호';

comment on column public.branch_summaries.branch_name is '업체명 (제휴사명)';

comment on column public.branch_summaries.region is '지역 (주소에서 추출)';

comment on column public.branch_summaries.review_count is '총 리뷰 개수';

comment on column public.branch_summaries.avg_rating is '평균 평점 (1.00 ~ 5.00)';

comment on column public.branch_summaries.keyword_1 is 'TOP 1 키워드';

comment on column public.branch_summaries.keyword_2 is 'TOP 2 키워드';

comment on column public.branch_summaries.keyword_3 is 'TOP 3 키워드';

comment on column public.branch_summaries.summary_1m is '최근 1개월 리뷰 기반 AI 요약';

comment on column public.branch_summaries.summary_3m is '최근 3개월 리뷰 기반 AI 요약';

comment on column public.branch_summaries.summary_6m is '최근 6개월 리뷰 기반 AI 요약';

comment on column public.branch_summaries.summary_1y is '최근 1년 리뷰 기반 AI 요약';

comment on column public.branch_summaries.summary_all is '전체 기간 리뷰 기반 AI 요약';

alter table public.branch_summaries
    owner to postgres;

grant select, update, usage on sequence public.branch_summaries_id_seq to anon;

grant select, update, usage on sequence public.branch_summaries_id_seq to authenticated;

grant select, update, usage on sequence public.branch_summaries_id_seq to service_role;

create index idx_branch_summaries_branch_id
    on public.branch_summaries (branch_id);

create index idx_branch_summaries_status
    on public.branch_summaries (status);

create index idx_branch_summaries_updated_at
    on public.branch_summaries (updated_at desc);

create index idx_summaries_status_region
    on public.branch_summaries (status, region);

create index idx_summaries_avg_rating
    on public.branch_summaries (avg_rating);

create index idx_summaries_review_count
    on public.branch_summaries (review_count);

create index idx_summaries_pending
    on public.branch_summaries ((pending_summaries IS NOT NULL AND pending_summaries <> '{}'::jsonb));

grant delete, insert, references, select, trigger, truncate, update on public.branch_summaries to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_summaries to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_summaries to service_role;

create table public.branch_reviews
(
    id                 bigserial
        primary key,
    review_id          integer
        unique,
    branch_id          integer not null,
    branch_name        varchar(100),
    company_name       varchar(100),
    content            text,
    rating_service     numeric(2, 1),
    rating_car         numeric(2, 1),
    rating_convenience numeric(2, 1),
    review_date        timestamp with time zone,
    car_model          varchar(100),
    rent_type          varchar(20),
    created_at         timestamp with time zone default now(),
    sentiment          varchar(20),
    is_new             boolean                  default false
);

comment on table public.branch_reviews is '원본 리뷰 데이터 (지점별 그룹화)';

comment on column public.branch_reviews.review_id is '리뷰번호 (원본 엑셀의 PK)';

comment on column public.branch_reviews.branch_id is '지점번호';

comment on column public.branch_reviews.branch_name is '지점명';

comment on column public.branch_reviews.company_name is '업체명';

comment on column public.branch_reviews.content is '리뷰 내용';

comment on column public.branch_reviews.rating_service is '지점평점(친절/편의성) 1-5';

comment on column public.branch_reviews.rating_car is '차량평점 1-5';

comment on column public.branch_reviews.rating_convenience is '인수/반납편의성 1-5';

comment on column public.branch_reviews.review_date is '리뷰 등록일시';

comment on column public.branch_reviews.car_model is '차량모델';

comment on column public.branch_reviews.rent_type is '렌트타입 (SHORT, SUBSCRIPTION 등)';

alter table public.branch_reviews
    owner to postgres;

grant select, update, usage on sequence public.branch_reviews_id_seq to anon;

grant select, update, usage on sequence public.branch_reviews_id_seq to authenticated;

grant select, update, usage on sequence public.branch_reviews_id_seq to service_role;

create index idx_reviews_sentiment
    on public.branch_reviews (sentiment);

create index idx_reviews_branch_sentiment
    on public.branch_reviews (branch_id, sentiment);

create index idx_branch_reviews_is_new
    on public.branch_reviews (is_new)
    where (is_new = true);

create index idx_reviews_branch_date
    on public.branch_reviews (branch_id asc, review_date desc);

create index idx_branch_reviews_sentiment_filter
    on public.branch_reviews (branch_id asc, sentiment asc, review_date desc);

create index idx_branch_reviews_review_date
    on public.branch_reviews (review_date);

create index idx_branch_reviews_branch_company
    on public.branch_reviews (branch_id, company_name)
    where (company_name IS NOT NULL);

grant delete, insert, references, select, trigger, truncate, update on public.branch_reviews to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_reviews to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_reviews to service_role;

create table public.branch_reports
(
    id               bigserial
        primary key,
    branch_id        bigint not null,
    branch_name      text   not null,
    affiliate_name   text,
    period_start     date   not null,
    period_end       date   not null,
    total_reviews    integer                  default 0,
    report_data      jsonb  not null,
    created_at       timestamp with time zone default now(),
    updated_at       timestamp with time zone default now(),
    is_viewed        boolean                  default false,
    viewed_at        timestamp with time zone,
    version          integer                  default 1,
    pdf_storage_path text,
    constraint uq_branch_reports_period
        unique (branch_id, period_start, period_end)
);

comment on table public.branch_reports is '지점별 AI 리포트 저장 테이블';

comment on column public.branch_reports.report_data is '전체 리포트 데이터 (JSON)';

comment on column public.branch_reports.is_viewed is '사용자 조회 여부';

comment on column public.branch_reports.viewed_at is '최초 조회 시간';

comment on column public.branch_reports.version is '동일 기간 리포트 버전 (재생성 시 증가)';

alter table public.branch_reports
    owner to postgres;

grant select, update, usage on sequence public.branch_reports_id_seq to anon;

grant select, update, usage on sequence public.branch_reports_id_seq to authenticated;

grant select, update, usage on sequence public.branch_reports_id_seq to service_role;

create index idx_branch_reports_branch_id
    on public.branch_reports (branch_id);

create index idx_branch_reports_period
    on public.branch_reports (period_start, period_end);

create index idx_branch_reports_created_at
    on public.branch_reports (created_at desc);

create unique index idx_branch_reports_unique
    on public.branch_reports (branch_id, period_start, period_end, version);

create index idx_branch_reports_unviewed
    on public.branch_reports (is_viewed)
    where (is_viewed = false);

grant delete, insert, references, select, trigger, truncate, update on public.branch_reports to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_reports to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_reports to service_role;

create table public.report_jobs
(
    id            uuid                     default gen_random_uuid() not null
        primary key,
    branch_id     integer                                            not null,
    period_start  date                                               not null,
    period_end    date                                               not null,
    status        varchar(20)              default 'pending'::character varying
        constraint report_jobs_status_check
            check ((status)::text = ANY
                   ((ARRAY ['pending'::character varying, 'processing'::character varying, 'completed'::character varying, 'failed'::character varying])::text[])),
    progress      integer                  default 0
        constraint report_jobs_progress_check
            check ((progress >= 0) AND (progress <= 100)),
    error_message text,
    report_id     integer,
    created_at    timestamp with time zone default now(),
    updated_at    timestamp with time zone default now()
);

alter table public.report_jobs
    owner to postgres;

create index idx_report_jobs_branch_id
    on public.report_jobs (branch_id);

create index idx_report_jobs_status
    on public.report_jobs (status);

create index idx_report_jobs_created_at
    on public.report_jobs (created_at desc);

create index idx_report_jobs_branch_period_status
    on public.report_jobs (branch_id, period_start, period_end, status);

create index idx_report_jobs_status_updated
    on public.report_jobs (status, updated_at);

grant delete, insert, references, select, trigger, truncate, update on public.report_jobs to anon;

grant delete, insert, references, select, trigger, truncate, update on public.report_jobs to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.report_jobs to service_role;

create table public.categories
(
    id            serial
        primary key,
    name          varchar(100) not null
        unique,
    description   text                     default ''::text,
    color         varchar(20)              default '#667eea'::character varying,
    display_order integer                  default 0,
    is_active     boolean                  default true,
    created_at    timestamp with time zone default now(),
    updated_at    timestamp with time zone default now()
);

alter table public.categories
    owner to postgres;

grant select, update, usage on sequence public.categories_id_seq to anon;

grant select, update, usage on sequence public.categories_id_seq to authenticated;

grant select, update, usage on sequence public.categories_id_seq to service_role;

create table public.tags
(
    id             serial
        primary key,
    name           varchar(50) not null
        unique,
    category_id    integer
        constraint fk_tags_category
            references public.categories
            on delete set null,
    sentiment      varchar(10)              default 'positive'::character varying,
    is_active      boolean                  default true,
    usage_count    integer                  default 0,
    created_at     timestamp with time zone default now(),
    updated_at     timestamp with time zone default now(),
    group_name     varchar(50),
    color          varchar(7)               default '#667eea'::character varying,
    sentiment_type text                     default 'positive'::text,
    deleted_at     timestamp with time zone,
    tag_type       varchar(10)
        constraint tags_tag_type_check
            check ((tag_type)::text = ANY ((ARRAY ['company'::character varying, 'vehicle'::character varying])::text[]))
);

comment on table public.tags is '정제된 키워드 태그';

comment on column public.tags.tag_type is '상위 분류: company(업체), vehicle(차량)';

alter table public.tags
    owner to postgres;

grant select, update, usage on sequence public.tags_id_seq to anon;

grant select, update, usage on sequence public.tags_id_seq to authenticated;

grant select, update, usage on sequence public.tags_id_seq to service_role;

create index idx_tags_category
    on public.tags (category_id);

create index idx_tags_sentiment
    on public.tags (sentiment);

create index idx_tags_active
    on public.tags (is_active)
    where (is_active = true);

create index idx_tags_name
    on public.tags (name);

create index idx_tags_group
    on public.tags (group_name);

grant delete, insert, references, select, trigger, truncate, update on public.tags to anon;

grant delete, insert, references, select, trigger, truncate, update on public.tags to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.tags to service_role;

create table public.branch_tags
(
    id             serial
        primary key,
    branch_id      integer                                                   not null,
    tag_id         integer
        references public.tags
            on delete cascade,
    period_type    varchar(10)              default 'all'::character varying not null,
    count          integer                  default 0,
    weighted_score numeric(10, 2)           default 0,
    rank           integer,
    updated_at     timestamp with time zone default now(),
    positive_count integer                  default 0,
    negative_count integer                  default 0,
    neutral_count  integer                  default 0,
    unique (branch_id, tag_id, period_type)
)
    with (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);

comment on table public.branch_tags is '지점별 태그 집계 (기간별)';

alter table public.branch_tags
    owner to postgres;

grant select, update, usage on sequence public.branch_tags_id_seq to anon;

grant select, update, usage on sequence public.branch_tags_id_seq to authenticated;

grant select, update, usage on sequence public.branch_tags_id_seq to service_role;

create index idx_branch_tags_tag
    on public.branch_tags (tag_id);

create index idx_branch_tags_branch_period
    on public.branch_tags (branch_id, period_type);

create index idx_branch_tags_branch
    on public.branch_tags (branch_id);

create index idx_branch_tags_sentiment
    on public.branch_tags (branch_id, tag_id, positive_count, negative_count);

grant delete, insert, references, select, trigger, truncate, update on public.branch_tags to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_tags to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_tags to service_role;

create table public.keyword_mappings
(
    id         serial
        primary key,
    keyword    text not null
        unique,
    tag_id     integer
        references public.tags,
    is_auto    boolean                  default true,
    confidence double precision         default 1.0,
    created_at timestamp with time zone default now()
)
    with (autovacuum_vacuum_scale_factor = 0.05, autovacuum_analyze_scale_factor = 0.02);

alter table public.keyword_mappings
    owner to postgres;

grant select, update, usage on sequence public.keyword_mappings_id_seq to anon;

grant select, update, usage on sequence public.keyword_mappings_id_seq to authenticated;

grant select, update, usage on sequence public.keyword_mappings_id_seq to service_role;

grant delete, insert, references, select, trigger, truncate, update on public.keyword_mappings to anon;

grant delete, insert, references, select, trigger, truncate, update on public.keyword_mappings to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.keyword_mappings to service_role;

grant delete, insert, references, select, trigger, truncate, update on public.categories to anon;

grant delete, insert, references, select, trigger, truncate, update on public.categories to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.categories to service_role;

create table public.branch_summary_log
(
    id           serial
        primary key,
    branch_id    integer                                                         not null,
    period_key   varchar(10)                                                     not null,
    review_count integer                  default 0                              not null,
    triggered_by varchar(20)              default 'scheduled'::character varying not null,
    created_at   timestamp with time zone default now()                          not null
);

comment on table public.branch_summary_log is '업체별 요약 생성 이력';

comment on column public.branch_summary_log.period_key is '요약 기간 (1m/3m/6m/1y)';

comment on column public.branch_summary_log.triggered_by is '트리거 타입 (volume: 100개 이상, scheduled: 기간 도달)';

alter table public.branch_summary_log
    owner to postgres;

grant select, update, usage on sequence public.branch_summary_log_id_seq to anon;

grant select, update, usage on sequence public.branch_summary_log_id_seq to authenticated;

grant select, update, usage on sequence public.branch_summary_log_id_seq to service_role;

create index idx_branch_summary_log_branch_id
    on public.branch_summary_log (branch_id);

create index idx_branch_summary_log_created_at
    on public.branch_summary_log (created_at desc);

grant delete, insert, references, select, trigger, truncate, update on public.branch_summary_log to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_summary_log to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_summary_log to service_role;

create table public.branch_scheduler_settings
(
    branch_id       integer                                                       not null
        primary key,
    summary_cycle   varchar(20)              default 'monthly'::character varying not null,
    min_reviews     integer                  default 30                           not null,
    auto_approve    boolean                  default false                        not null,
    last_summary_at timestamp with time zone,
    next_summary_at timestamp with time zone,
    created_at      timestamp with time zone default now()                        not null,
    updated_at      timestamp with time zone default now()                        not null
);

comment on table public.branch_scheduler_settings is '업체별 요약 스케줄러 설정';

comment on column public.branch_scheduler_settings.summary_cycle is '요약 주기 (weekly/biweekly/monthly)';

comment on column public.branch_scheduler_settings.min_reviews is '요약 생성 최소 리뷰 수';

comment on column public.branch_scheduler_settings.auto_approve is '자동 승인 여부';

alter table public.branch_scheduler_settings
    owner to postgres;

create index idx_branch_scheduler_settings_next_summary
    on public.branch_scheduler_settings (next_summary_at)
    where (next_summary_at IS NOT NULL);

grant delete, insert, references, select, trigger, truncate, update on public.branch_scheduler_settings to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_scheduler_settings to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_scheduler_settings to service_role;

create table public.sync_metadata
(
    id               serial
        primary key,
    sync_type        varchar(50) not null
        unique,
    last_sync_at     timestamp with time zone,
    is_running       boolean                  default false,
    lock_acquired_at timestamp with time zone,
    updated_at       timestamp with time zone default now(),
    created_at       timestamp with time zone default now()
);

comment on table public.sync_metadata is '동기화 메타데이터 (마지막 동기화 시간, 락 상태)';

comment on column public.sync_metadata.sync_type is '동기화 유형 (new_review, daily_sync 등)';

comment on column public.sync_metadata.is_running is '동시 실행 방지 플래그';

comment on column public.sync_metadata.lock_acquired_at is '락 획득 시간 (데드락 감지용)';

alter table public.sync_metadata
    owner to postgres;

grant select, update, usage on sequence public.sync_metadata_id_seq to anon;

grant select, update, usage on sequence public.sync_metadata_id_seq to authenticated;

grant select, update, usage on sequence public.sync_metadata_id_seq to service_role;

create index idx_sync_metadata_sync_type
    on public.sync_metadata (sync_type);

grant delete, insert, references, select, trigger, truncate, update on public.sync_metadata to anon;

grant delete, insert, references, select, trigger, truncate, update on public.sync_metadata to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.sync_metadata to service_role;

create table public.branch_summaries_history
(
    id           serial
        primary key,
    branch_id    integer not null,
    summary_all  text,
    summary_1y   text,
    summary_6m   text,
    summary_3m   text,
    summary_1m   text,
    keywords     jsonb                    default '[]'::jsonb,
    review_count integer                  default 0,
    avg_rating   numeric(3, 2),
    generated_by varchar(50)              default 'scheduler'::character varying,
    created_at   timestamp with time zone default now()
);

comment on table public.branch_summaries_history is '요약 변경 히스토리 (시간 경과에 따른 변화 추적)';

alter table public.branch_summaries_history
    owner to postgres;

grant select, update, usage on sequence public.branch_summaries_history_id_seq to anon;

grant select, update, usage on sequence public.branch_summaries_history_id_seq to authenticated;

grant select, update, usage on sequence public.branch_summaries_history_id_seq to service_role;

create index idx_summaries_history_branch_id
    on public.branch_summaries_history (branch_id);

create index idx_summaries_history_created_at
    on public.branch_summaries_history (created_at desc);

grant delete, insert, references, select, trigger, truncate, update on public.branch_summaries_history to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_summaries_history to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_summaries_history to service_role;

create table public.audit_logs
(
    id         bigserial
        primary key,
    user_id    text,
    action     text not null
        constraint audit_logs_action_check
            check (action = ANY (ARRAY ['INSERT'::text, 'UPDATE'::text, 'DELETE'::text])),
    table_name text not null,
    record_id  text,
    old_data   jsonb,
    new_data   jsonb,
    ip_address inet,
    created_at timestamp with time zone default now()
);

alter table public.audit_logs
    owner to postgres;

grant select, update, usage on sequence public.audit_logs_id_seq to anon;

grant select, update, usage on sequence public.audit_logs_id_seq to authenticated;

grant select, update, usage on sequence public.audit_logs_id_seq to service_role;

create index idx_audit_logs_table
    on public.audit_logs (table_name);

create index idx_audit_logs_created
    on public.audit_logs (created_at);

create index idx_audit_logs_user
    on public.audit_logs (user_id);

grant delete, insert, references, select, trigger, truncate, update on public.audit_logs to anon;

grant delete, insert, references, select, trigger, truncate, update on public.audit_logs to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.audit_logs to service_role;

create table public.review_tag_mappings
(
    id              bigserial
        primary key,
    review_id       integer     not null,
    tag_id          integer     not null
        references public.tags,
    sentiment       varchar(10) not null
        constraint review_tag_mappings_sentiment_check
            check ((sentiment)::text = ANY
                   ((ARRAY ['positive'::character varying, 'negative'::character varying, 'neutral'::character varying])::text[])),
    confidence      double precision         default 1.0
        constraint review_tag_mappings_confidence_check
            check ((confidence >= (0.0)::double precision) AND (confidence <= (1.0)::double precision)),
    source          varchar(20) not null
        constraint review_tag_mappings_source_check
            check ((source)::text = ANY
                   ((ARRAY ['rule'::character varying, 'embedding'::character varying, 'manual'::character varying, 'pipeline'::character varying])::text[])),
    matched_keyword text,
    created_at      timestamp with time zone default now(),
    unique (review_id, tag_id, sentiment)
);

comment on table public.review_tag_mappings is '리뷰별 태그 매핑 (개별 추적, 재집계 가능)';

comment on column public.review_tag_mappings.review_id is 'branch_reviews.review_id 참조';

comment on column public.review_tag_mappings.confidence is '매핑 신뢰도 0.0~1.0';

comment on column public.review_tag_mappings.source is '매핑 소스: rule(규칙), embedding(임베딩), manual(수동)';

alter table public.review_tag_mappings
    owner to postgres;

grant select, update, usage on sequence public.review_tag_mappings_id_seq to anon;

grant select, update, usage on sequence public.review_tag_mappings_id_seq to authenticated;

grant select, update, usage on sequence public.review_tag_mappings_id_seq to service_role;

create index idx_rtm_review_id
    on public.review_tag_mappings (review_id);

create index idx_rtm_tag_sentiment
    on public.review_tag_mappings (tag_id, sentiment);

grant delete, insert, references, select, trigger, truncate, update on public.review_tag_mappings to anon;

grant delete, insert, references, select, trigger, truncate, update on public.review_tag_mappings to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.review_tag_mappings to service_role;

create table public.monthly_rating_stats
(
    id                     bigserial
        primary key,
    branch_id              integer    not null,
    period                 varchar(7) not null,
    avg_rating_service     numeric(4, 2),
    avg_rating_car         numeric(4, 2),
    avg_rating_convenience numeric(4, 2),
    avg_rating_total       numeric(4, 2),
    review_count           integer                  default 0,
    updated_at             timestamp with time zone default now(),
    unique (branch_id, period)
);

comment on table public.monthly_rating_stats is '지점별 월별 별점 집계';

comment on column public.monthly_rating_stats.period is 'yyyy-mm 형식 (예: 2026-01)';

alter table public.monthly_rating_stats
    owner to postgres;

grant select, update, usage on sequence public.monthly_rating_stats_id_seq to anon;

grant select, update, usage on sequence public.monthly_rating_stats_id_seq to authenticated;

grant select, update, usage on sequence public.monthly_rating_stats_id_seq to service_role;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_rating_stats to anon;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_rating_stats to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_rating_stats to service_role;

create table public.monthly_sentiment_stats
(
    id             bigserial
        primary key,
    branch_id      integer    not null,
    period         varchar(7) not null,
    positive_count integer                  default 0,
    negative_count integer                  default 0,
    neutral_count  integer                  default 0,
    updated_at     timestamp with time zone default now(),
    review_count   integer                  default 0,
    unique (branch_id, period)
);

comment on table public.monthly_sentiment_stats is '지점별 월별 감정 집계';

comment on column public.monthly_sentiment_stats.period is 'yyyy-mm 형식 (예: 2026-01)';

alter table public.monthly_sentiment_stats
    owner to postgres;

grant select, update, usage on sequence public.monthly_sentiment_stats_id_seq to anon;

grant select, update, usage on sequence public.monthly_sentiment_stats_id_seq to authenticated;

grant select, update, usage on sequence public.monthly_sentiment_stats_id_seq to service_role;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_sentiment_stats to anon;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_sentiment_stats to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_sentiment_stats to service_role;

create table public.monthly_tag_stats
(
    id             bigserial
        primary key,
    branch_id      integer    not null,
    period         varchar(7) not null,
    tag_id         integer    not null
        references public.tags,
    positive_count integer                  default 0,
    negative_count integer                  default 0,
    neutral_count  integer                  default 0,
    updated_at     timestamp with time zone default now(),
    unique (branch_id, period, tag_id)
);

comment on table public.monthly_tag_stats is '지점별 월별 태그 집계';

comment on column public.monthly_tag_stats.period is 'yyyy-mm 형식 (예: 2026-01)';

alter table public.monthly_tag_stats
    owner to postgres;

grant select, update, usage on sequence public.monthly_tag_stats_id_seq to anon;

grant select, update, usage on sequence public.monthly_tag_stats_id_seq to authenticated;

grant select, update, usage on sequence public.monthly_tag_stats_id_seq to service_role;

create index idx_mts_branch_period
    on public.monthly_tag_stats (branch_id, period);

create index idx_mts_tag
    on public.monthly_tag_stats (tag_id);

grant delete, insert, references, select, trigger, truncate, update on public.monthly_tag_stats to anon;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_tag_stats to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_tag_stats to service_role;

create table public.car_models_master
(
    id           serial
        primary key,
    model_name   varchar(100) not null
        unique,
    category     varchar(30),
    manufacturer varchar(50),
    created_at   timestamp with time zone default now(),
    updated_at   timestamp with time zone default now()
);

comment on table public.car_models_master is '차량 모델 마스터 테이블';

comment on column public.car_models_master.category is '차종 카테고리 (세단, SUV, 경차 등)';

comment on column public.car_models_master.manufacturer is '제조사 (현대, 기아 등)';

alter table public.car_models_master
    owner to postgres;

grant select, update, usage on sequence public.car_models_master_id_seq to anon;

grant select, update, usage on sequence public.car_models_master_id_seq to authenticated;

grant select, update, usage on sequence public.car_models_master_id_seq to service_role;

grant delete, insert, references, select, trigger, truncate, update on public.car_models_master to anon;

grant delete, insert, references, select, trigger, truncate, update on public.car_models_master to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.car_models_master to service_role;

create table public.branch_car_models
(
    branch_id    integer not null,
    car_model_id integer not null
        references public.car_models_master,
    created_at   timestamp with time zone default now(),
    primary key (branch_id, car_model_id)
);

comment on table public.branch_car_models is '지점-차량 모델 매핑 테이블';

alter table public.branch_car_models
    owner to postgres;

grant delete, insert, references, select, trigger, truncate, update on public.branch_car_models to anon;

grant delete, insert, references, select, trigger, truncate, update on public.branch_car_models to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.branch_car_models to service_role;

create table public.monthly_car_model_tag_stats
(
    id             bigserial
        primary key,
    car_model_id   integer    not null
        references public.car_models_master,
    period         varchar(7) not null,
    tag_id         integer    not null
        references public.tags,
    positive_count integer                  default 0,
    negative_count integer                  default 0,
    neutral_count  integer                  default 0,
    updated_at     timestamp with time zone default now(),
    unique (car_model_id, period, tag_id)
);

comment on table public.monthly_car_model_tag_stats is '차량 모델별 월별 태그 감정 집계';

comment on column public.monthly_car_model_tag_stats.period is 'yyyy-mm 형식 (예: 2026-01)';

alter table public.monthly_car_model_tag_stats
    owner to postgres;

grant select, update, usage on sequence public.monthly_car_model_tag_stats_id_seq to anon;

grant select, update, usage on sequence public.monthly_car_model_tag_stats_id_seq to authenticated;

grant select, update, usage on sequence public.monthly_car_model_tag_stats_id_seq to service_role;

create index idx_mcmts_model_period
    on public.monthly_car_model_tag_stats (car_model_id, period);

grant delete, insert, references, select, trigger, truncate, update on public.monthly_car_model_tag_stats to anon;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_car_model_tag_stats to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.monthly_car_model_tag_stats to service_role;

create table public.report_results
(
    id            bigserial
        primary key,
    report_id     varchar(100)                                                   not null,
    period        varchar(20)              default '1m'::character varying       not null,
    response_data jsonb                                                          not null,
    status_code   integer,
    triggered_by  varchar(20)              default 'schedule'::character varying not null,
    created_at    timestamp with time zone default now()
);

alter table public.report_results
    owner to postgres;

grant select, update, usage on sequence public.report_results_id_seq to anon;

grant select, update, usage on sequence public.report_results_id_seq to authenticated;

grant select, update, usage on sequence public.report_results_id_seq to service_role;

create index idx_report_results_report_id
    on public.report_results (report_id);

create index idx_report_results_created_at
    on public.report_results (created_at);

grant delete, insert, references, select, trigger, truncate, update on public.report_results to anon;

grant delete, insert, references, select, trigger, truncate, update on public.report_results to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.report_results to service_role;

create table public.new_reviews
(
    id                 bigserial
        primary key,
    review_id          integer not null
        unique,
    branch_id          integer not null,
    branch_name        varchar,
    company_name       varchar,
    content            text,
    rating_service     double precision,
    rating_car         double precision,
    rating_convenience double precision,
    review_date        timestamp with time zone,
    car_model          varchar,
    rent_type          varchar,
    created_at         timestamp with time zone default now()
);

alter table public.new_reviews
    owner to postgres;

grant select, update, usage on sequence public.new_reviews_id_seq to anon;

grant select, update, usage on sequence public.new_reviews_id_seq to authenticated;

grant select, update, usage on sequence public.new_reviews_id_seq to service_role;

create index idx_new_reviews_branch_id
    on public.new_reviews (branch_id);

create index idx_new_reviews_review_date
    on public.new_reviews (review_date desc);

grant delete, insert, references, select, trigger, truncate, update on public.new_reviews to anon;

grant delete, insert, references, select, trigger, truncate, update on public.new_reviews to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.new_reviews to service_role;

create table public.schedule_groups
(
    id              bigserial
        primary key,
    workflow_id     text                                               not null,
    group_name      text                     default '기본 그룹'::text     not null,
    cron_expression text                     default '0 6 * * *'::text not null,
    created_at      timestamp with time zone default now(),
    updated_at      timestamp with time zone default now()
);

alter table public.schedule_groups
    owner to postgres;

grant select, update, usage on sequence public.schedule_groups_id_seq to anon;

grant select, update, usage on sequence public.schedule_groups_id_seq to authenticated;

grant select, update, usage on sequence public.schedule_groups_id_seq to service_role;

create table public.scheduler_targets
(
    id          bigserial
        primary key,
    workflow_id text    not null,
    branch_id   integer not null,
    branch_name text                     default ''::text,
    created_at  timestamp with time zone default now(),
    group_id    bigint
        references public.schedule_groups
            on delete cascade,
    constraint scheduler_targets_group_branch_unique
        unique (group_id, branch_id)
);

comment on table public.scheduler_targets is '스케줄러 워크플로별 대상 지점 설정';

alter table public.scheduler_targets
    owner to postgres;

grant select, update, usage on sequence public.scheduler_targets_id_seq to anon;

grant select, update, usage on sequence public.scheduler_targets_id_seq to authenticated;

grant select, update, usage on sequence public.scheduler_targets_id_seq to service_role;

create index idx_scheduler_targets_workflow
    on public.scheduler_targets (workflow_id);

grant delete, insert, references, select, trigger, truncate, update on public.scheduler_targets to anon;

grant delete, insert, references, select, trigger, truncate, update on public.scheduler_targets to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.scheduler_targets to service_role;

create index idx_schedule_groups_workflow
    on public.schedule_groups (workflow_id);

grant delete, insert, references, select, trigger, truncate, update on public.schedule_groups to anon;

grant delete, insert, references, select, trigger, truncate, update on public.schedule_groups to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.schedule_groups to service_role;

create table public.prompt_presets
(
    id                   serial
        primary key,
    name                 varchar(100)                                                      not null,
    description          text                     default ''::text,
    branch_type          varchar(20)              default NULL::character varying
        constraint chk_branch_type
            check ((branch_type IS NULL) OR ((branch_type)::text = ANY
                                             ((ARRAY ['airport'::character varying, 'tourist'::character varying, 'city'::character varying])::text[]))),
    analysis_perspective varchar(30)              default 'operational'::character varying not null
        constraint chk_perspective
            check ((analysis_perspective)::text = ANY
                   ((ARRAY ['operational'::character varying, 'marketing'::character varying, 'executive'::character varying, 'customer_service'::character varying, 'investor'::character varying, 'comparative'::character varying])::text[])),
    tone                 varchar(30)              default 'analytical'::character varying  not null
        constraint chk_tone
            check ((tone)::text = ANY
                   ((ARRAY ['analytical'::character varying, 'friendly'::character varying, 'formal'::character varying, 'concise'::character varying, 'data_driven'::character varying, 'narrative'::character varying])::text[])),
    detail_level         varchar(20)              default 'standard'::character varying    not null
        constraint chk_detail_level
            check ((detail_level)::text = ANY
                   ((ARRAY ['brief'::character varying, 'standard'::character varying, 'detailed'::character varying])::text[])),
    focus_areas          jsonb                    default '[]'::jsonb,
    custom_instruction   text                     default ''::text,
    temperature          double precision         default 0.5,
    summary_max_length   integer                  default 600,
    eval_max_length      integer                  default 250,
    is_default           boolean                  default false,
    is_active            boolean                  default true,
    display_order        integer                  default 0,
    created_at           timestamp with time zone default now(),
    updated_at           timestamp with time zone default now()
);

alter table public.prompt_presets
    owner to postgres;

grant select, update, usage on sequence public.prompt_presets_id_seq to anon;

grant select, update, usage on sequence public.prompt_presets_id_seq to authenticated;

grant select, update, usage on sequence public.prompt_presets_id_seq to service_role;

create index idx_prompt_presets_branch_type
    on public.prompt_presets (branch_type);

create index idx_prompt_presets_active
    on public.prompt_presets (is_active)
    where (is_active = true);

grant delete, insert, references, select, trigger, truncate, update on public.prompt_presets to anon;

grant delete, insert, references, select, trigger, truncate, update on public.prompt_presets to authenticated;

grant delete, insert, references, select, trigger, truncate, update on public.prompt_presets to service_role;

