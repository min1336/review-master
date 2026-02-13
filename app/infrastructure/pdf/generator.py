"""
PDF 생성기

FPDF2를 사용하여 리포트를 PDF로 생성합니다.
시스템 의존성 없이 pip만으로 설치 가능합니다.
한글 폰트는 시스템 폰트(fonts-nanum)를 사용합니다.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF

if TYPE_CHECKING:
    from services.report_service import ReportData

logger = logging.getLogger(__name__)


class PDFGenerator:
    """FPDF2 기반 PDF 생성기"""

    # 시스템 폰트 경로 (우선순위 순)
    FONT_PATHS = [
        # Linux (apt-get install fonts-nanum)
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        # macOS (brew install font-nanum-gothic)
        Path("/Library/Fonts/NanumGothic.ttf"),
        Path("/Library/Fonts/NanumGothicBold.ttf"),
        # Local fallback (app/fonts/)
        Path(__file__).resolve().parent.parent.parent / "fonts" / "NanumGothic-Regular.ttf",
        Path(__file__).resolve().parent.parent.parent / "fonts" / "NanumGothic-Bold.ttf",
    ]

    # ================================================================
    # 디자인 시스템 상수
    # ================================================================

    # 브랜드 컬러
    BRAND_PRIMARY = (30, 64, 175)       # 딥 블루
    BRAND_LIGHT = (219, 234, 254)       # 라이트 블루 배경
    BRAND_DARK = (15, 23, 42)           # 거의 블랙 (텍스트)

    # 시맨틱 컬러
    GREEN = (16, 185, 129)
    GREEN_LIGHT = (209, 250, 229)       # 연두 배경
    RED = (239, 68, 68)
    RED_LIGHT = (254, 226, 226)         # 연분홍 배경
    AMBER = (245, 158, 11)
    AMBER_LIGHT = (254, 243, 199)

    # 중립 컬러
    GREY_50 = (249, 250, 251)
    GREY_100 = (243, 244, 246)
    GREY_200 = (229, 231, 235)
    GREY_300 = (209, 213, 219)
    GREY_400 = (156, 163, 175)
    GREY_500 = (107, 114, 128)
    GREY_600 = (75, 85, 99)
    GREY_BG = GREY_200
    GREY_LIGHT = GREY_100
    GREY_LINE = GREY_300
    GREY_TEXT = GREY_500

    # 레이아웃 상수
    PAGE_W = 210
    MARGIN = 15
    CONTENT_W = PAGE_W - MARGIN * 2  # 180mm

    # 타이포그래피
    FONT_TITLE = 15
    FONT_SECTION = 11
    FONT_BODY = 8
    FONT_SMALL = 7.5
    FONT_TINY = 7

    # 간격
    SECTION_GAP = 6
    CARD_PAD = 4
    LINE_H = 4.5

    # 컴포넌트 치수 (M-3: 매직넘버 상수화)
    AXIS_NAME_W = 27           # 평가축 이름 셀 너비 (mm)
    BAR_WIDTH_RATIO = 0.55     # 인라인 프로그레스 바 비율
    EST_CHARS_PER_LINE = 45    # AI 인사이트 줄당 예상 글자수

    # 클래스 레벨 폰트 캐시 (H-3: 매 인스턴스 파일시스템 탐색 방지)
    _font_cache: dict[str, Path | None] | None = None

    def __init__(self):
        if PDFGenerator._font_cache is None:
            PDFGenerator._font_cache = self._discover_fonts()
        self._font_regular: Path | None = PDFGenerator._font_cache.get("regular")
        self._font_bold: Path | None = PDFGenerator._font_cache.get("bold")

    @classmethod
    def _discover_fonts(cls) -> dict[str, Path | None]:
        """시스템에서 사용 가능한 폰트 찾기 (최초 1회만 실행)"""
        cache: dict[str, Path | None] = {"regular": None, "bold": None}
        for path in cls.FONT_PATHS:
            if not path.exists():
                continue

            if "Bold" in path.name or "bold" in path.name:
                if cache["bold"] is None:
                    cache["bold"] = path
            else:
                if cache["regular"] is None:
                    cache["regular"] = path

            if cache["regular"] and cache["bold"]:
                break

        if cache["regular"]:
            logger.info(f"Found Korean font: {cache['regular']}")
        else:
            logger.warning(
                "Korean font not found. Install with: "
                "apt-get install fonts-nanum (Linux) or "
                "brew install font-nanum-gothic (macOS)"
            )
        return cache

    def _setup_pdf(self) -> tuple[FPDF, str]:
        """PDF 인스턴스 생성 및 폰트 설정"""
        pdf = FPDF()

        if self._font_regular:
            pdf.add_font("NanumGothic", "", str(self._font_regular))
            if self._font_bold:
                pdf.add_font("NanumGothic", "B", str(self._font_bold))
            else:
                pdf.add_font("NanumGothic", "B", str(self._font_regular))
            font = "NanumGothic"
        else:
            font = "Helvetica"

        return pdf, font

    # ================================================================
    # 도형 프리미티브
    # ================================================================

    def _draw_rounded_rect(
        self,
        pdf: FPDF,
        x: float,
        y: float,
        w: float,
        h: float,
        r: float = 2,
        style: str = "F",
    ) -> None:
        """둥근 모서리 사각형 그리기 (arc + line)"""
        r = min(r, w / 2, h / 2)
        # 4개 모서리 호 + 4개 직선
        # FPDF2에서 arc는 불안정할 수 있으므로, r이 작으면 일반 rect로 폴백
        if r < 1:
            pdf.rect(x, y, w, h, style=style)
            return

        # 곡선 없이 일반 rect 사용 (FPDF2 호환성 최우선)
        # 시각적으로 충분한 카드 효과는 배경색+여백으로 달성
        pdf.rect(x, y, w, h, style=style)

    def _draw_progress_bar(
        self,
        pdf: FPDF,
        x: float,
        y: float,
        bar_w: float,
        bar_h: float,
        ratio: int,
        fill_color: tuple | None = None,
        bg_color: tuple | None = None,
    ) -> None:
        """프로그레스 바 그리기 (그라데이션 색상 지원)"""
        fill_c = fill_color or self._ratio_color(ratio)
        bg_c = bg_color or self.GREY_200
        fill_w = bar_w * (ratio / 100)

        # 배경 (전체)
        pdf.set_fill_color(*bg_c)
        pdf.rect(x, y, bar_w, bar_h, style="F")

        # 채움
        if fill_w > 0:
            pdf.set_fill_color(*fill_c)
            pdf.rect(x, y, fill_w, bar_h, style="F")

    def _ratio_color(self, ratio: int) -> tuple[int, int, int]:
        """비율에 따른 색상 (빨강 → 노랑 → 초록)"""
        if ratio >= 70:
            return self.GREEN
        if ratio >= 40:
            return self.AMBER
        return self.RED

    # ================================================================
    # 헤더 / 섹션 / 푸터 컴포넌트
    # ================================================================

    def _draw_header(
        self,
        pdf: FPDF,
        font: str,
        branch_name: str,
        period_start: str,
        period_end: str,
        total_reviews: int,
    ) -> None:
        """브랜드 헤더 — 컬러 배경 + 흰 텍스트 + stat cards"""
        m = self.MARGIN
        w = self.CONTENT_W

        # 헤더 배경 박스
        header_h = 28
        pdf.set_fill_color(*self.BRAND_PRIMARY)
        self._draw_rounded_rect(pdf, m, pdf.get_y(), w, header_h, r=2, style="F")

        # 타이틀
        title_y = pdf.get_y() + 5
        pdf.set_xy(m, title_y)
        pdf.set_font(font, "B", self.FONT_TITLE)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(w, 8, f"{branch_name} AI 컨설팅 리포트", align="C", new_x="LMARGIN", new_y="NEXT")

        # 서브 텍스트
        pdf.set_font(font, "", self.FONT_BODY)
        pdf.set_text_color(219, 234, 254)  # BRAND_LIGHT
        pdf.cell(
            w, 5,
            f"분석 기간: {period_start} ~ {period_end}",
            align="C", new_x="LMARGIN", new_y="NEXT",
        )

        pdf.set_text_color(0, 0, 0)  # 복원
        pdf.set_y(pdf.get_y() + 4)

        # Stat cards (기간 / 리뷰 수)
        card_w = 85
        card_h = 14
        gap = w - card_w * 2
        card_y = pdf.get_y()

        # 카드 1: 분석 기간
        self._draw_stat_card(
            pdf, font, m, card_y, card_w, card_h,
            label="분석 기간",
            value=f"{period_start} ~ {period_end}",
        )
        # 카드 2: 총 리뷰
        self._draw_stat_card(
            pdf, font, m + card_w + gap, card_y, card_w, card_h,
            label="총 리뷰 수",
            value=f"{total_reviews}건",
        )

        pdf.set_y(card_y + card_h + self.SECTION_GAP)

    def _draw_stat_card(
        self,
        pdf: FPDF,
        font: str,
        x: float,
        y: float,
        w: float,
        h: float,
        label: str,
        value: str,
    ) -> None:
        """미니 통계 카드"""
        pdf.set_fill_color(*self.GREY_50)
        pdf.set_draw_color(*self.GREY_300)
        pdf.rect(x, y, w, h, style="FD")

        pdf.set_xy(x + 3, y + 1.5)
        pdf.set_font(font, "", self.FONT_TINY)
        pdf.set_text_color(*self.GREY_500)
        pdf.cell(w - 6, 4, label)

        pdf.set_xy(x + 3, y + 6)
        pdf.set_font(font, "B", self.FONT_BODY)
        pdf.set_text_color(*self.BRAND_DARK)
        pdf.cell(w - 6, 5, value)

        pdf.set_text_color(0, 0, 0)

    def _draw_section_header(
        self, pdf: FPDF, font: str, w: float, margin: float, title: str,
        accent_color: tuple | None = None,
    ) -> None:
        """섹션 제목 — 좌측 accent bar + 배경"""
        accent = accent_color or self.BRAND_PRIMARY
        y = pdf.get_y()

        # 배경 바
        bg_h = 8
        pdf.set_fill_color(*self.GREY_50)
        pdf.rect(margin, y, w, bg_h, style="F")

        # 좌측 accent bar (3px 너비)
        bar_w = 1.2
        pdf.set_fill_color(*accent)
        pdf.rect(margin, y, bar_w, bg_h, style="F")

        # 텍스트
        pdf.set_xy(margin + bar_w + 3, y + 1)
        pdf.set_font(font, "B", self.FONT_SECTION)
        pdf.set_text_color(*self.BRAND_DARK)
        pdf.cell(w - bar_w - 3, 6, title)
        pdf.set_text_color(0, 0, 0)

        pdf.set_y(y + bg_h + 3)

    def _draw_axis_bars(
        self, pdf: FPDF, font: str, axes: list, margin: float, w: float
    ) -> None:
        """축별 게이지 바 (가로 배치, 개선된 디자인)"""
        if not axes:
            return
        bar_w = 40
        bar_h = 3.5
        gap = 8
        ax_y = pdf.get_y()

        for i, ax in enumerate(axes):
            ax_x = margin + i * (bar_w + gap + self.AXIS_NAME_W + 5)
            if ax_x + bar_w + self.AXIS_NAME_W > self.PAGE_W - margin:
                break

            # 축 이름
            pdf.set_xy(ax_x, ax_y)
            pdf.set_font(font, "", self.FONT_SMALL)
            pdf.set_text_color(*self.GREY_600)
            pdf.cell(self.AXIS_NAME_W, 4, ax.name, new_x="END")

            # 게이지 바 (비율에 따른 색상)
            self._draw_progress_bar(
                pdf, ax_x + 27, ax_y + 0.3, bar_w, bar_h, ax.positive_ratio,
            )

            # 퍼센트 텍스트
            pdf.set_xy(ax_x + 27 + bar_w + 2, ax_y)
            pdf.set_font(font, "B", self.FONT_SMALL)
            color = self._ratio_color(ax.positive_ratio)
            pdf.set_text_color(*color)
            pdf.cell(10, 4, f"{ax.positive_ratio}%")
            pdf.set_text_color(0, 0, 0)

        pdf.set_y(ax_y + 8)

    def _draw_two_column(
        self,
        pdf: FPDF,
        font: str,
        w: float,
        margin: float,
        left_title: str,
        left_items: list[str],
        right_title: str,
        right_items: list[str],
        left_color: tuple,
        right_color: tuple,
        left_marker: str = "\u25cf",   # ●
        right_marker: str = "\u25b2",  # ▲
    ) -> None:
        """2열 카드 레이아웃 (잘한점/개선점)"""
        half = (w - 6) / 2
        card_gap = 6
        col_y = pdf.get_y()

        # ── 왼쪽 카드 ──
        left_x = margin
        self._draw_column_card(
            pdf, font, left_x, col_y, half,
            title=left_title,
            items=left_items,
            color=left_color,
            bg_color=self.GREEN_LIGHT,
            marker=left_marker,
        )
        left_end_y = pdf.get_y()

        # ── 오른쪽 카드 ──
        right_x = margin + half + card_gap
        pdf.set_y(col_y)
        self._draw_column_card(
            pdf, font, right_x, col_y, half,
            title=right_title,
            items=right_items,
            color=right_color,
            bg_color=self.RED_LIGHT,
            marker=right_marker,
        )
        right_end_y = pdf.get_y()

        pdf.set_y(max(left_end_y, right_end_y) + 3)

    def _draw_column_card(
        self,
        pdf: FPDF,
        font: str,
        x: float,
        y: float,
        w: float,
        title: str,
        items: list[str],
        color: tuple,
        bg_color: tuple,
        marker: str,
    ) -> None:
        """단일 열 카드 (제목 + 항목 리스트)"""
        pad = self.CARD_PAD
        item_h = self.LINE_H
        title_h = 6
        # 카드 높이 계산
        n_items = min(len(items), 5)
        card_h = title_h + pad + (n_items * item_h) + pad

        # 카드 배경
        pdf.set_fill_color(*bg_color)
        self._draw_rounded_rect(pdf, x, y, w, card_h, r=2, style="F")

        # 제목 바
        pdf.set_fill_color(*color)
        pdf.rect(x, y, w, title_h, style="F")
        pdf.set_xy(x + pad, y + 1)
        pdf.set_font(font, "B", self.FONT_SMALL)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(w - pad * 2, 4, f"  {title}")
        pdf.set_text_color(0, 0, 0)

        # 항목
        pdf.set_font(font, "", self.FONT_TINY)
        item_y = y + title_h + 2
        for item in items[:5]:
            pdf.set_xy(x + pad, item_y)
            pdf.set_text_color(*self.GREY_600)
            pdf.cell(5, item_h, marker)
            pdf.set_text_color(*self.BRAND_DARK)
            pdf.cell(w - pad * 2 - 5, item_h, f" {item}")
            item_y += item_h

        pdf.set_text_color(0, 0, 0)
        pdf.set_y(y + card_h)

    def _draw_vehicle_table(
        self,
        pdf: FPDF,
        font: str,
        margin: float,
        w: float,
        title: str,
        vehicles: list,
        color: tuple,
        ratio_label: str,
    ) -> None:
        """차량 테이블 (헤더 컬러 + zebra striping + 인라인 바)"""
        if not vehicles:
            return

        col_model = w * 0.30
        col_tags = w * 0.40
        col_ratio = w * 0.30
        row_h = 5.5

        # 테이블 헤더
        header_y = pdf.get_y()
        pdf.set_fill_color(*color)
        pdf.rect(margin, header_y, w, row_h + 1, style="F")

        pdf.set_xy(margin, header_y + 0.5)
        pdf.set_font(font, "B", self.FONT_TINY)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(col_model, row_h, f"  {title}", new_x="END")
        pdf.cell(col_tags, row_h, "태그", new_x="END")
        pdf.cell(col_ratio, row_h, ratio_label, align="C")
        pdf.set_text_color(0, 0, 0)

        pdf.set_y(header_y + row_h + 1)

        # 테이블 행
        pdf.set_font(font, "", self.FONT_TINY)
        for i, v in enumerate(vehicles[:5]):
            row_y = pdf.get_y()

            # Zebra striping
            if i % 2 == 0:
                pdf.set_fill_color(*self.GREY_50)
                pdf.rect(margin, row_y, w, row_h, style="F")

            pdf.set_xy(margin, row_y)
            pdf.set_font(font, "B" if i == 0 else "", self.FONT_TINY)
            pdf.set_text_color(*self.BRAND_DARK)
            pdf.cell(col_model, row_h, f"  {v.model}", new_x="END")

            # 태그
            pdf.set_font(font, "", self.FONT_TINY)
            pdf.set_text_color(*self.GREY_600)
            tags_text = ", ".join(v.tags[:3]) if v.tags else "-"
            pdf.cell(col_tags, row_h, tags_text, new_x="END")

            # 비율 + 인라인 프로그레스 바
            ratio_x = margin + col_model + col_tags
            bar_w = col_ratio * self.BAR_WIDTH_RATIO
            bar_x = ratio_x + 2
            bar_y = row_y + 1.5
            self._draw_progress_bar(
                pdf, bar_x, bar_y, bar_w, 2.5, v.ratio, fill_color=color,
            )
            pdf.set_xy(bar_x + bar_w + 2, row_y)
            pdf.set_font(font, "B", self.FONT_TINY)
            pdf.set_text_color(*color)
            pdf.cell(col_ratio - bar_w - 4, row_h, f"{v.ratio}%")

            pdf.set_text_color(0, 0, 0)
            pdf.set_y(row_y + row_h)

        pdf.ln(2)

    def _draw_ai_insight(
        self, pdf: FPDF, font: str, w: float, text: str,
    ) -> None:
        """AI 인사이트 텍스트 박스"""
        if not text:
            return
        m = self.MARGIN
        y = pdf.get_y()
        pad = 3

        # 배경
        pdf.set_fill_color(*self.BRAND_LIGHT)
        # 텍스트 높이 예측 (대략 줄 수 기반)
        est_lines = max(1, math.ceil(len(text) / self.EST_CHARS_PER_LINE))
        box_h = est_lines * 4 + pad * 2

        pdf.rect(m, y, w, box_h, style="F")

        # 좌측 accent
        pdf.set_fill_color(*self.BRAND_PRIMARY)
        pdf.rect(m, y, 1, box_h, style="F")

        pdf.set_xy(m + pad + 1, y + pad)
        pdf.set_font(font, "", self.FONT_SMALL)
        pdf.set_text_color(*self.GREY_600)
        pdf.multi_cell(w - pad * 2 - 1, 4, text)
        pdf.set_text_color(0, 0, 0)

        # multi_cell이 실제로 차지한 높이가 box_h보다 클 수 있으므로
        actual_end = pdf.get_y() + pad
        pdf.set_y(max(y + box_h, actual_end) + 3)

    def _draw_footer(
        self, pdf: FPDF, font: str, margin: float, generated_at: str
    ) -> None:
        """브랜드 푸터"""
        y = pdf.get_y() + 4
        w = self.CONTENT_W

        # 상단 구분선
        pdf.set_draw_color(*self.GREY_300)
        pdf.line(margin, y, self.PAGE_W - margin, y)

        # 푸터 텍스트
        pdf.set_xy(margin, y + 2)
        pdf.set_font(font, "B", self.FONT_TINY)
        pdf.set_text_color(*self.BRAND_PRIMARY)
        pdf.cell(w / 2, 5, "Carmore AI")

        pdf.set_xy(margin, y + 2)
        pdf.set_font(font, "", self.FONT_TINY)
        pdf.set_text_color(*self.GREY_400)
        pdf.cell(w, 5, generated_at, align="R")

        pdf.set_text_color(0, 0, 0)

    # ================================================================
    # PDF 생성
    # ================================================================

    def generate_simple(self, report: ReportData) -> bytes:
        """
        3-섹션 구조 PDF 생성

        새 포맷(affiliate_evaluation 존재) -> 요약/업체평가/차량평가
        구 포맷 -> 기존 레거시 렌더링
        """
        if report.affiliate_evaluation:
            return self._generate_new_format(report)
        return self._generate_legacy_format(report)

    def _generate_new_format(self, report: ReportData) -> bytes:
        """3-섹션 구조 PDF (요약 / 업체 평가 / 차량 평가) -- 멀티페이지 지원"""
        pdf, font = self._setup_pdf()
        pdf.set_auto_page_break(auto=True, margin=20)
        pdf.add_page()

        margin = self.MARGIN
        w = self.CONTENT_W
        pdf.set_left_margin(margin)
        pdf.set_right_margin(margin)

        # -- 헤더 --
        self._draw_header(
            pdf, font, report.branch_name,
            report.period_start, report.period_end,
            report.total_reviews,
        )

        # -- 섹션 1: 요약 --
        self._draw_section_header(pdf, font, w, margin, "요약")
        pdf.set_font(font, "", self.FONT_BODY)
        pdf.set_text_color(*self.GREY_600)
        pdf.multi_cell(w, self.LINE_H, report.period_summary or "요약 없음")
        pdf.set_text_color(0, 0, 0)
        pdf.ln(self.SECTION_GAP)

        # -- 섹션 2: 업체 평가 --
        aff = report.affiliate_evaluation
        if aff:
            self._draw_section_header(pdf, font, w, margin, "업체 평가")
            self._draw_axis_bars(pdf, font, aff.axes or [], margin, w)

            left_items = [
                f"{tag.tag_name} ({tag.ratio}%, {tag.count}건)"
                for tag in (aff.top_positive or [])[:5]
            ]
            right_items = [
                f"{tag.tag_name} (부정 {tag.ratio}%, {tag.count}건)"
                for tag in (aff.top_negative or [])[:5]
            ]
            self._draw_two_column(
                pdf, font, w, margin,
                "잘한점", left_items,
                "개선점", right_items,
                self.GREEN, self.RED,
            )

            self._draw_ai_insight(pdf, font, w, aff.ai_text)

        # -- 섹션 3: 차량 평가 --
        veh = report.vehicle_evaluation
        if veh:
            self._draw_section_header(pdf, font, w, margin, "차량 평가")
            self._draw_axis_bars(pdf, font, veh.axes or [], margin, w)

            # 호평 차량 테이블
            self._draw_vehicle_table(
                pdf, font, margin, w,
                title="호평 차량",
                vehicles=veh.top_liked or [],
                color=self.GREEN,
                ratio_label="호평률",
            )

            # 불만 차량 테이블
            self._draw_vehicle_table(
                pdf, font, margin, w,
                title="불만 차량",
                vehicles=veh.top_disliked or [],
                color=self.RED,
                ratio_label="불만률",
            )

            self._draw_ai_insight(pdf, font, w, veh.ai_text)

        # -- 푸터 --
        self._draw_footer(pdf, font, margin, report.generated_at)

        return bytes(pdf.output())

    def _generate_legacy_format(self, report: ReportData) -> bytes:
        """기존 포맷 PDF (하위호환)"""
        pdf, font = self._setup_pdf()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        # 제목
        pdf.set_font(font, "B", 16)
        pdf.cell(0, 10, f"{report.branch_name} AI 컨설팅 리포트", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        pdf.set_font(font, "", 10)
        pdf.cell(0, 6, f"분석 기간: {report.period_start} ~ {report.period_end}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"총 리뷰 수: {report.total_reviews}건", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(8)

        # 구분선
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(8)

        w = 190

        # 기간 요약
        pdf.set_font(font, "B", 12)
        pdf.cell(w, 8, "기간별 요약", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "", 10)
        pdf.multi_cell(w, 6, report.period_summary or "요약 없음")
        pdf.ln(6)

        # 현상유지 / 보완필요
        if report.strengths or report.improvements:
            half = (w - 6) / 2

            pdf.set_font(font, "B", 10)
            pdf.cell(half, 6, "현상유지", new_x="RIGHT")
            pdf.set_x(pdf.get_x() + 6)
            pdf.cell(half, 6, "보완필요", new_x="LMARGIN", new_y="NEXT")

            pdf.set_font(font, "", 9)
            max_rows = max(len(report.strengths), len(report.improvements))
            for i in range(max_rows):
                s_text = f"  {report.strengths[i]}" if i < len(report.strengths) else ""
                i_text = f"  {report.improvements[i]}" if i < len(report.improvements) else ""
                pdf.cell(half, 5, s_text, new_x="RIGHT")
                pdf.set_x(pdf.get_x() + 6)
                pdf.cell(half, 5, i_text, new_x="LMARGIN", new_y="NEXT")
            pdf.ln(6)

        # 차량별 평가 분석
        if report.vehicle_analysis:
            pdf.set_font(font, "B", 12)
            pdf.cell(w, 8, "차량별 평가 분석", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

            vehicles = sorted(
                report.vehicle_analysis, key=lambda v: v.count, reverse=True,
            )

            top_n = min(3, len(vehicles))
            sorted_best = sorted(vehicles, key=lambda v: v.like_ratio, reverse=True)
            top_best = sorted_best[:top_n]

            best_models = {v.model for v in top_best}
            sorted_worst = sorted(vehicles, key=lambda v: v.dislike_ratio, reverse=True)
            top_worst = [
                v for v in sorted_worst
                if v.model not in best_models and v.dislike_ratio > 0
            ][:top_n]

            pdf.set_font(font, "B", 10)
            pdf.cell(w, 6, "  우수 차량", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font(font, "", 9)
            for v in top_best:
                praise = f", 특히 '{v.top_praise}' 평가 우수" if v.top_praise else ""
                pdf.cell(
                    w, 5,
                    f"    {v.model}({v.count}건) - 호평률 {v.like_ratio}%{praise}",
                    new_x="LMARGIN", new_y="NEXT",
                )
            pdf.ln(2)

            if top_worst:
                pdf.set_font(font, "B", 10)
                pdf.cell(w, 6, "  개선 필요 차량", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font(font, "", 9)
                for v in top_worst:
                    issue = f", '{v.top_issue}' 관련 불만 집중" if v.top_issue else ""
                    pdf.cell(
                        w, 5,
                        f"    {v.model}({v.count}건) - 불만률 {v.dislike_ratio}%{issue}",
                        new_x="LMARGIN", new_y="NEXT",
                    )
                pdf.ln(2)

            pdf.ln(3)

            # 전체 차량 현황 테이블
            pdf.set_font(font, "B", 9)
            pdf.cell(w, 6, f"  전체 차량 현황 ({len(vehicles)}대)", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

            left_x = pdf.l_margin
            col_gap = 4
            half_w = (w - col_gap) / 2
            model_w = 35
            praise_w = 29
            issue_w = half_w - model_w - praise_w
            row_h = 4.5
            right_x = left_x + half_w + col_gap

            mid = (len(vehicles) + 1) // 2
            left_list = vehicles[:mid]
            right_list = vehicles[mid:]

            pdf.set_font(font, "B", 7)
            pdf.set_fill_color(240, 240, 240)

            pdf.set_x(left_x)
            pdf.cell(model_w, row_h, " 차량(건수)", border=1, fill=True)
            pdf.cell(praise_w, row_h, " 호평", border=1, fill=True)
            pdf.cell(issue_w, row_h, " 불만", border=1, fill=True)

            if right_list:
                pdf.set_x(right_x)
                pdf.cell(model_w, row_h, " 차량(건수)", border=1, fill=True)
                pdf.cell(praise_w, row_h, " 호평", border=1, fill=True)
                pdf.cell(issue_w, row_h, " 불만", border=1, fill=True)
            pdf.ln(row_h)

            pdf.set_font(font, "", 7)
            for i in range(len(left_list)):
                lv = left_list[i]
                pdf.set_x(left_x)
                pdf.cell(model_w, row_h, f" {lv.model}({lv.count})", border=1)
                pdf.cell(praise_w, row_h, f" {lv.top_praise or '-'}", border=1)
                pdf.cell(issue_w, row_h, f" {lv.top_issue or '-'}", border=1)

                if i < len(right_list):
                    rv = right_list[i]
                    pdf.set_x(right_x)
                    pdf.cell(model_w, row_h, f" {rv.model}({rv.count})", border=1)
                    pdf.cell(praise_w, row_h, f" {rv.top_praise or '-'}", border=1)
                    pdf.cell(issue_w, row_h, f" {rv.top_issue or '-'}", border=1)

                pdf.ln(row_h)
            pdf.ln(4)

        # 푸터
        pdf.ln(10)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        pdf.set_font(font, "", 8)
        pdf.cell(0, 5, f"Generated by Carmore AI  |  {report.generated_at}", align="C")

        return bytes(pdf.output())
