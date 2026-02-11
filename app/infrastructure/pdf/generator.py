"""
PDF 생성기

FPDF2를 사용하여 리포트를 PDF로 생성합니다.
시스템 의존성 없이 pip만으로 설치 가능합니다.
한글 폰트는 시스템 폰트(fonts-nanum)를 사용합니다.
"""

from __future__ import annotations

import logging
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

    # 색상 상수
    GREEN = (16, 185, 129)
    RED = (239, 68, 68)
    GREY_BG = (229, 231, 235)
    GREY_LIGHT = (240, 240, 240)
    GREY_LINE = (200, 200, 200)
    GREY_TEXT = (120, 120, 120)

    def __init__(self):
        self._font_regular: Path | None = None
        self._font_bold: Path | None = None
        self._find_fonts()

    def _find_fonts(self) -> None:
        """시스템에서 사용 가능한 폰트 찾기"""
        for path in self.FONT_PATHS:
            if not path.exists():
                continue

            if "Bold" in path.name or "bold" in path.name:
                if self._font_bold is None:
                    self._font_bold = path
            else:
                if self._font_regular is None:
                    self._font_regular = path

            if self._font_regular and self._font_bold:
                break

        if self._font_regular:
            logger.info(f"Found Korean font: {self._font_regular}")
        else:
            logger.warning(
                "Korean font not found. Install with: "
                "apt-get install fonts-nanum (Linux) or "
                "brew install font-nanum-gothic (macOS)"
            )

    def _setup_pdf(self) -> tuple[FPDF, str]:
        """PDF 인스턴스 생성 및 폰트 설정"""
        pdf = FPDF()
        pdf.set_auto_page_break(auto=False)

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

    def _draw_progress_bar(
        self,
        pdf: FPDF,
        x: float,
        y: float,
        bar_w: float,
        bar_h: float,
        ratio: int,
    ) -> None:
        """프로그레스 바 그리기"""
        fill_w = bar_w * (ratio / 100)
        # 채워진 부분 (초록)
        pdf.set_fill_color(*self.GREEN)
        if fill_w > 0:
            pdf.rect(x, y, fill_w, bar_h, style="F")
        # 빈 부분 (회색)
        pdf.set_fill_color(*self.GREY_BG)
        if fill_w < bar_w:
            pdf.rect(x + fill_w, y, bar_w - fill_w, bar_h, style="F")

    def generate_simple(self, report: ReportData) -> bytes:
        """
        3-섹션 구조 PDF 생성 (한 페이지)

        새 포맷(affiliate_evaluation 존재) → 요약/업체평가/차량평가
        구 포맷 → 기존 레거시 렌더링

        Args:
            report: 리포트 데이터

        Returns:
            PDF 바이트 데이터
        """
        if report.affiliate_evaluation:
            return self._generate_new_format(report)
        return self._generate_legacy_format(report)

    def _generate_new_format(self, report: ReportData) -> bytes:
        """3-섹션 구조 PDF (요약 / 업체 평가 / 차량 평가) — 한 페이지"""
        pdf, font = self._setup_pdf()
        pdf.add_page()

        # 마진/너비
        margin = 15
        pdf.set_left_margin(margin)
        pdf.set_right_margin(margin)
        w = 210 - margin * 2  # 180mm 가용 너비

        # ── 헤더 (제목 + 기간 + 리뷰 수) ──
        pdf.set_font(font, "B", 14)
        pdf.cell(w, 8, f"{report.branch_name} AI 컨설팅 리포트", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "", 9)
        pdf.cell(w, 5, f"분석 기간: {report.period_start} ~ {report.period_end}  |  총 리뷰: {report.total_reviews}건", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)

        # 구분선
        pdf.set_draw_color(*self.GREY_LINE)
        pdf.line(margin, pdf.get_y(), 210 - margin, pdf.get_y())
        pdf.ln(4)

        # ── 섹션 1: 요약 ──
        pdf.set_font(font, "B", 10)
        pdf.cell(w, 6, "요약", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "", 8)
        pdf.multi_cell(w, 4.5, report.period_summary or "요약 없음")
        pdf.ln(4)

        # ── 섹션 2: 업체 평가 ──
        aff = report.affiliate_evaluation
        if aff:
            pdf.set_draw_color(*self.GREY_BG)
            pdf.line(margin, pdf.get_y(), 210 - margin, pdf.get_y())
            pdf.ln(3)

            pdf.set_font(font, "B", 10)
            pdf.cell(w, 6, "업체 평가", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

            # 축별 게이지 바 (가로 배치)
            axes = aff.axes or []
            if axes:
                bar_w = 40
                bar_h = 3
                gap = 8
                ax_y = pdf.get_y()

                for i, ax in enumerate(axes):
                    ax_x = margin + i * (bar_w + gap + 30)
                    if ax_x + bar_w + 25 > 210 - margin:
                        break

                    # 축 이름
                    pdf.set_xy(ax_x, ax_y)
                    pdf.set_font(font, "", 7.5)
                    pdf.cell(25, 4, ax.name, new_x="END")

                    # 프로그레스 바
                    self._draw_progress_bar(pdf, ax_x + 25, ax_y + 0.5, bar_w, bar_h, ax.positive_ratio)

                    # 비율 텍스트
                    pdf.set_xy(ax_x + 25 + bar_w + 2, ax_y)
                    pdf.set_font(font, "B", 7.5)
                    pdf.cell(10, 4, f"{ax.positive_ratio}%")

                pdf.set_y(ax_y + 7)

            # 잘한점 / 개선점 2열
            half = (w - 4) / 2
            col_y = pdf.get_y()

            # 잘한점 (왼쪽)
            pdf.set_xy(margin, col_y)
            pdf.set_fill_color(230, 250, 240)  # 연한 초록 배경
            pdf.set_font(font, "B", 7.5)
            pdf.set_text_color(*self.GREEN)
            pdf.cell(half, 4.5, "  잘한점", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

            pdf.set_font(font, "", 7)
            for tag in (aff.top_positive or [])[:5]:
                pdf.set_x(margin)
                pdf.cell(half, 4, f"  {tag.tag_name}({tag.ratio}%, {tag.count}건)", new_x="LMARGIN", new_y="NEXT")

            left_end_y = pdf.get_y()

            # 개선점 (오른쪽)
            pdf.set_xy(margin + half + 4, col_y)
            pdf.set_font(font, "B", 7.5)
            pdf.set_text_color(*self.RED)
            pdf.cell(half, 4.5, "  개선점", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

            pdf.set_font(font, "", 7)
            for tag in (aff.top_negative or [])[:5]:
                pdf.set_x(margin + half + 4)
                pdf.cell(half, 4, f"  {tag.tag_name}(부정 {tag.ratio}%, {tag.count}건)", new_x="LMARGIN", new_y="NEXT")

            right_end_y = pdf.get_y()
            pdf.set_y(max(left_end_y, right_end_y) + 2)

            # AI 평가 텍스트
            if aff.ai_text:
                pdf.set_font(font, "", 7.5)
                pdf.set_text_color(*self.GREY_TEXT)
                pdf.multi_cell(w, 4, aff.ai_text)
                pdf.set_text_color(0, 0, 0)
                pdf.ln(3)

        # ── 섹션 3: 차량 평가 ──
        veh = report.vehicle_evaluation
        if veh:
            pdf.set_draw_color(*self.GREY_BG)
            pdf.line(margin, pdf.get_y(), 210 - margin, pdf.get_y())
            pdf.ln(3)

            pdf.set_font(font, "B", 10)
            pdf.cell(w, 6, "차량 평가", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)

            # 축별 게이지 바
            axes = veh.axes or []
            if axes:
                bar_w = 40
                bar_h = 3
                gap = 8
                ax_y = pdf.get_y()

                for i, ax in enumerate(axes):
                    ax_x = margin + i * (bar_w + gap + 30)
                    if ax_x + bar_w + 25 > 210 - margin:
                        break

                    pdf.set_xy(ax_x, ax_y)
                    pdf.set_font(font, "", 7.5)
                    pdf.cell(25, 4, ax.name, new_x="END")

                    self._draw_progress_bar(pdf, ax_x + 25, ax_y + 0.5, bar_w, bar_h, ax.positive_ratio)

                    pdf.set_xy(ax_x + 25 + bar_w + 2, ax_y)
                    pdf.set_font(font, "B", 7.5)
                    pdf.cell(10, 4, f"{ax.positive_ratio}%")

                pdf.set_y(ax_y + 7)

            # 호평 차량 / 불만 차량 2열
            half = (w - 4) / 2
            col_y = pdf.get_y()

            # 호평 차량 (왼쪽)
            pdf.set_xy(margin, col_y)
            pdf.set_font(font, "B", 7.5)
            pdf.set_text_color(*self.GREEN)
            pdf.cell(half, 4.5, "  호평 차량", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

            pdf.set_font(font, "", 7)
            for v in (veh.top_liked or [])[:5]:
                tags_str = ", ".join(v.tags[:2]) if v.tags else ""
                text = f"  {v.model}(호평 {v.ratio}%) {tags_str}"
                pdf.set_x(margin)
                pdf.cell(half, 4, text, new_x="LMARGIN", new_y="NEXT")

            left_end_y = pdf.get_y()

            # 불만 차량 (오른쪽)
            pdf.set_xy(margin + half + 4, col_y)
            pdf.set_font(font, "B", 7.5)
            pdf.set_text_color(*self.RED)
            pdf.cell(half, 4.5, "  불만 차량", new_x="LMARGIN", new_y="NEXT")
            pdf.set_text_color(0, 0, 0)

            pdf.set_font(font, "", 7)
            for v in (veh.top_disliked or [])[:5]:
                tags_str = ", ".join(v.tags[:2]) if v.tags else ""
                text = f"  {v.model}(불만 {v.ratio}%) {tags_str}"
                pdf.set_x(margin + half + 4)
                pdf.cell(half, 4, text, new_x="LMARGIN", new_y="NEXT")

            right_end_y = pdf.get_y()
            pdf.set_y(max(left_end_y, right_end_y) + 2)

            # AI 평가 텍스트
            if veh.ai_text:
                pdf.set_font(font, "", 7.5)
                pdf.set_text_color(*self.GREY_TEXT)
                pdf.multi_cell(w, 4, veh.ai_text)
                pdf.set_text_color(0, 0, 0)

        # ── 푸터 ──
        pdf.set_y(max(pdf.get_y() + 6, 280))
        pdf.set_draw_color(*self.GREY_LINE)
        pdf.line(margin, pdf.get_y(), 210 - margin, pdf.get_y())
        pdf.ln(3)
        pdf.set_font(font, "", 8)
        pdf.cell(0, 5, f"Generated by Carmore AI  |  {report.generated_at}", align="C")

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
