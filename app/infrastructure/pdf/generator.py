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

    def generate_simple(self, report: ReportData) -> bytes:
        """
        단순 텍스트 PDF 생성 (레이아웃 없이 AI 결과만)

        - 차트, 색상, 그리드 없음
        - 순수 텍스트만 출력
        - Docker 환경에서 가볍게 사용 가능

        Args:
            report: 리포트 데이터

        Returns:
            PDF 바이트 데이터
        """
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)

        # 폰트 설정
        if self._font_regular:
            pdf.add_font("NanumGothic", "", str(self._font_regular))
            if self._font_bold:
                pdf.add_font("NanumGothic", "B", str(self._font_bold))
            else:
                pdf.add_font("NanumGothic", "B", str(self._font_regular))
            font = "NanumGothic"
        else:
            font = "Helvetica"

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

        # 유효 너비 (A4: 210mm, 마진 10mm 양쪽)
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

        # 차량별 평가 분석 (하이라이트 + 전체 축소 테이블)
        if report.vehicle_analysis:
            pdf.set_font(font, "B", 12)
            pdf.cell(w, 8, "차량별 평가 분석", new_x="LMARGIN", new_y="NEXT")
            pdf.ln(2)

            vehicles = sorted(
                report.vehicle_analysis, key=lambda v: v.count, reverse=True,
            )

            # --- 1단: 주목할 차량 하이라이트 ---
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

            # --- 2단: 전체 차량 현황 (축소 2열 테이블) ---
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

            # 헤더
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

            # 데이터 행
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
