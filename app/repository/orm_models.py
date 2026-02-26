"""
SQLAlchemy ORM 모델 정의

코드에서 참조하는 테이블들의 ORM 클래스.
기존 Pydantic 모델(app/models/)은 DTO로 유지하고, ORM은 DB 접근 전용.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """SQLAlchemy ORM 베이스 클래스"""
    pass


# ============================================================
# 태그 시스템
# ============================================================


class CategoryORM(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text, default="")
    color: Mapped[str | None] = mapped_column(String(20), default="#667eea")
    display_order: Mapped[int | None] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tags: Mapped[list[TagORM]] = relationship(back_populates="category")


class TagORM(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    group_name: Mapped[str | None] = mapped_column(String(100))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    color: Mapped[str | None] = mapped_column(String(20), default="#667eea")
    sentiment: Mapped[str] = mapped_column(String(20), default="positive")
    tag_type: Mapped[str | None] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    category: Mapped[CategoryORM | None] = relationship(back_populates="tags")
    keyword_mappings: Mapped[list[KeywordMappingORM]] = relationship(
        back_populates="tag"
    )


class KeywordMappingORM(Base):
    __tablename__ = "keyword_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword: Mapped[str] = mapped_column(String(200), unique=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"))
    is_auto: Mapped[bool] = mapped_column(Boolean, default=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tag: Mapped[TagORM] = relationship(back_populates="keyword_mappings")


# ============================================================
# 지점 태그 통계
# ============================================================


class BranchTagORM(Base):
    __tablename__ = "branch_tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"))
    period_type: Mapped[str] = mapped_column(String(10), default="all")
    count: Mapped[int] = mapped_column(Integer, default=0)
    positive_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, default=0)
    weighted_score: Mapped[float | None] = mapped_column(Float, default=0)
    rank: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    tag: Mapped[TagORM] = relationship()


# ============================================================
# 리뷰
# ============================================================


class BranchReviewORM(Base):
    __tablename__ = "branch_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int | None] = mapped_column(Integer)
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    branch_name: Mapped[str | None] = mapped_column(String(200))
    company_name: Mapped[str | None] = mapped_column(String(200))
    content: Mapped[str | None] = mapped_column(Text)
    rating_service: Mapped[float | None] = mapped_column(Float)
    rating_car: Mapped[float | None] = mapped_column(Float)
    rating_convenience: Mapped[float | None] = mapped_column(Float)
    sentiment: Mapped[str | None] = mapped_column(String(20))
    car_model: Mapped[str | None] = mapped_column(String(100))
    rent_type: Mapped[str | None] = mapped_column(String(50))
    review_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_new: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ReviewTagMappingORM(Base):
    __tablename__ = "review_tag_mappings"

    id: Mapped[int] = mapped_column(primary_key=True)
    review_id: Mapped[int] = mapped_column(Integer, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"))
    sentiment: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(50))
    matched_keyword: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ============================================================
# 요약
# ============================================================


class BranchSummaryORM(Base):
    __tablename__ = "branch_summaries"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    branch_name: Mapped[str | None] = mapped_column(String(200))
    region: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str | None] = mapped_column(String(50))
    review_count: Mapped[int | None] = mapped_column(Integer, default=0)
    avg_rating: Mapped[float | None] = mapped_column(Float)
    keywords: Mapped[list | None] = mapped_column(JSONB)
    keyword_1: Mapped[str | None] = mapped_column(String(100))
    keyword_2: Mapped[str | None] = mapped_column(String(100))
    keyword_3: Mapped[str | None] = mapped_column(String(100))
    summary_all: Mapped[str | None] = mapped_column(Text)
    summary_1y: Mapped[str | None] = mapped_column(Text)
    summary_6m: Mapped[str | None] = mapped_column(Text)
    summary_3m: Mapped[str | None] = mapped_column(Text)
    summary_1m: Mapped[str | None] = mapped_column(Text)
    pending_summaries: Mapped[dict | None] = mapped_column(JSONB)
    ai_report_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BranchSummaryHistoryORM(Base):
    __tablename__ = "branch_summaries_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    summary_all: Mapped[str | None] = mapped_column(Text)
    summary_1y: Mapped[str | None] = mapped_column(Text)
    summary_6m: Mapped[str | None] = mapped_column(Text)
    summary_3m: Mapped[str | None] = mapped_column(Text)
    summary_1m: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list | None] = mapped_column(JSONB)
    review_count: Mapped[int | None] = mapped_column(Integer)
    avg_rating: Mapped[float | None] = mapped_column(Float)
    generated_by: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ============================================================
# 리포트
# ============================================================


class BranchReportORM(Base):
    __tablename__ = "branch_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    branch_name: Mapped[str | None] = mapped_column(String(200))
    affiliate_name: Mapped[str | None] = mapped_column(String(200))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    total_reviews: Mapped[int | None] = mapped_column(Integer)
    report_data: Mapped[dict | None] = mapped_column(JSONB)
    version: Mapped[int] = mapped_column(Integer, default=1)
    is_viewed: Mapped[bool] = mapped_column(Boolean, default=False)
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ReportJobORM(Base):
    __tablename__ = "report_jobs"

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid()
    )
    branch_id: Mapped[int] = mapped_column(Integer)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    report_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ============================================================
# 감정/별점 월별 통계
# ============================================================


class MonthlySentimentStatsORM(Base):
    __tablename__ = "monthly_sentiment_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[str] = mapped_column(String(7))  # "YYYY-MM"
    positive_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, default=0)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MonthlyRatingStatsORM(Base):
    __tablename__ = "monthly_rating_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[str] = mapped_column(String(7))
    avg_rating_service: Mapped[float | None] = mapped_column(Float)
    avg_rating_car: Mapped[float | None] = mapped_column(Float)
    avg_rating_convenience: Mapped[float | None] = mapped_column(Float)
    avg_rating_total: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MonthlyTagStatsORM(Base):
    __tablename__ = "monthly_tag_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    period: Mapped[str] = mapped_column(String(7))
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"))
    positive_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ============================================================
# 업체 / 차량 모델
# ============================================================


class AffiliateORM(Base):
    __tablename__ = "affiliates"

    id: Mapped[int] = mapped_column(primary_key=True)
    affiliate_index: Mapped[int | None] = mapped_column(Integer, unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    location_type: Mapped[str | None] = mapped_column(String(50))
    address: Mapped[str | None] = mapped_column(Text)
    phone: Mapped[str | None] = mapped_column(String(50))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarModelORM(Base):
    """car_models 테이블 (affiliate_repository에서 사용)"""
    __tablename__ = "car_models"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_id: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    name_en: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    brand: Mapped[str | None] = mapped_column(String(100))
    seats: Mapped[int | None] = mapped_column(Integer)
    fuel_type: Mapped[str | None] = mapped_column(String(50))
    transmission: Mapped[str | None] = mapped_column(String(50))
    image_url: Mapped[str | None] = mapped_column(Text)
    raw_data: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CarModelsMasterORM(Base):
    __tablename__ = "car_models_master"

    id: Mapped[int] = mapped_column(primary_key=True)
    model_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100))
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BranchCarModelORM(Base):
    __tablename__ = "branch_car_models"

    branch_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    car_model_id: Mapped[int] = mapped_column(
        ForeignKey("car_models_master.id"), primary_key=True
    )
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    car_model: Mapped[CarModelsMasterORM] = relationship()


class MonthlyCarModelTagStatsORM(Base):
    __tablename__ = "monthly_car_model_tag_stats"

    id: Mapped[int] = mapped_column(primary_key=True)
    car_model_id: Mapped[int] = mapped_column(
        ForeignKey("car_models_master.id"), index=True
    )
    period: Mapped[str] = mapped_column(String(7))
    tag_id: Mapped[int] = mapped_column(ForeignKey("tags.id"))
    positive_count: Mapped[int] = mapped_column(Integer, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, default=0)
    neutral_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ============================================================
# 시스템 관리
# ============================================================


class SyncMetadataORM(Base):
    __tablename__ = "sync_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    sync_type: Mapped[str] = mapped_column(String(50), unique=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_running: Mapped[bool] = mapped_column(Boolean, default=False)
    lock_acquired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BranchKeywordORM(Base):
    __tablename__ = "branch_keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, index=True)
    keyword: Mapped[str] = mapped_column(String(200))
    raw_count: Mapped[int] = mapped_column(Integer, default=0)
    count: Mapped[int] = mapped_column(Integer, default=0)
    weighted_score: Mapped[float] = mapped_column(Float, default=0)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class BranchSchedulerSettingsORM(Base):
    __tablename__ = "branch_scheduler_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    summary_cycle: Mapped[str | None] = mapped_column(String(50))
    min_reviews: Mapped[int | None] = mapped_column(Integer)
    auto_approve: Mapped[bool] = mapped_column(Boolean, default=False)
    last_summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_summary_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ============================================================
# 프롬프트 프리셋
# ============================================================


class PromptPresetORM(Base):
    __tablename__ = "prompt_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    system_prompt: Mapped[str | None] = mapped_column(Text)
    user_prompt_template: Mapped[str | None] = mapped_column(Text)
    branch_type: Mapped[str | None] = mapped_column(String(50))
    display_order: Mapped[int | None] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
