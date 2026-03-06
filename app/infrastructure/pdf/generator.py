"""
PDF 생성기

weasyprint를 사용하여 HTML 템플릿을 PDF로 변환합니다.
weasyprint 미설치 시 FPDF2로 fallback합니다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from fpdf import FPDF

if TYPE_CHECKING:
    from services.report_service import ReportData

logger = logging.getLogger(__name__)

# weasyprint 사용 가능 여부 (시스템 의존성 필요)
try:
    import weasyprint as _wp
    _HAS_WEASYPRINT = True
except (ImportError, OSError):
    _HAS_WEASYPRINT = False
    logger.info("weasyprint 미설치 — FPDF2 fallback 사용")


class PDFGenerator:
    """FPDF2 기반 PDF 생성기"""

    FONT_PATHS = [
        Path("/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
        Path("/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
        Path("/Library/Fonts/NanumGothic.ttf"),
        Path("/Library/Fonts/NanumGothicBold.ttf"),
        Path(__file__).resolve().parent.parent.parent / "fonts" / "NanumGothic-Regular.ttf",
        Path(__file__).resolve().parent.parent.parent / "fonts" / "NanumGothic-Bold.ttf",
    ]

    _font_cache: dict[str, Path | None] | None = None

    def __init__(self):
        if PDFGenerator._font_cache is None:
            PDFGenerator._font_cache = self._discover_fonts()
        self._font_regular: Path | None = PDFGenerator._font_cache.get("regular")
        self._font_bold: Path | None = PDFGenerator._font_cache.get("bold")

    @classmethod
    def _discover_fonts(cls) -> dict[str, Path | None]:
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
    # PDF 생성 (public)
    # ================================================================

    def generate_simple(self, report: ReportData) -> bytes:
        """PDF 생성 — weasyprint 우선, FPDF2 fallback"""
        if _HAS_WEASYPRINT:
            try:
                return self._generate_html_pdf(report)
            except Exception as e:
                logger.warning(f"weasyprint PDF 생성 실패, FPDF2 fallback: {e}")
        if isinstance(report.top_tags_detail, list):
            return self._generate_new_format(report)
        return self._generate_legacy_format(report)

    # ================================================================
    # HTML → PDF (weasyprint)
    # ================================================================

    _TEMPLATE_DIR = Path(__file__).resolve().parent.parent.parent / "templates" / "pdf"

    def _generate_html_pdf(self, report: ReportData) -> bytes:
        """Jinja2 HTML 템플릿을 weasyprint로 PDF 변환"""
        from jinja2 import Environment, FileSystemLoader

        env = Environment(
            loader=FileSystemLoader(str(self._TEMPLATE_DIR)),
            autoescape=True,
        )
        template = env.get_template("report_template.html")
        html_str = template.render(report=report)
        doc = _wp.HTML(string=html_str)
        return doc.write_pdf()

    # ================================================================
    # 심플 포맷 (3-섹션: 요약 / 업체 평가 / 차량 평가)
    # ================================================================

    def _generate_new_format(self, report: ReportData) -> bytes:
        pdf, font = self._setup_pdf()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        m = 15
        w = 180
        pdf.set_left_margin(m)
        pdf.set_right_margin(m)

        row = 5   # 기본 행 높이
        gap = 3   # 섹션 내 여백

        # ── 헤더 ──
        pdf.set_font(font, "B", 14)
        pdf.cell(w, 8, f"{report.branch_name} AI 컨설팅 리포트",
                 align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "", 9)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(w, 5, f"분석 기간: {report.period_start} ~ {report.period_end}  |  총 리뷰: {report.total_reviews}건",
                 align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_text_color(0, 0, 0)
        self._hr(pdf, m, w)

        # ── 1. 요약 ──
        if report.period_summary:
            self._section(pdf, font, "1. 요약")
            pdf.set_font(font, "", 9)
            pdf.multi_cell(w, row, report.period_summary)
            pdf.ln(gap)

        # ── 2. 업체 평가 ──
        aff = report.affiliate_evaluation
        if aff:
            self._section(pdf, font, "2. 업체 평가")

            # 잘한점 / 개선점 (1줄 요약)
            pos_tags = (aff.top_positive or [])[:5]
            if pos_tags:
                self._sub(pdf, font, "잘한점")
                pdf.set_font(font, "", 8)
                pos_line = ", ".join(f"{t.tag_name}({t.count}건)" for t in pos_tags)
                pdf.cell(w, 4.5, f"  {pos_line}",
                         new_x="LMARGIN", new_y="NEXT")
            pdf.ln(gap)

            neg_tags = (aff.top_negative or [])[:5]
            if neg_tags:
                self._sub(pdf, font, "개선점")
                pdf.set_font(font, "", 8)
                neg_line = ", ".join(f"{t.tag_name}({t.count}건)" for t in neg_tags)
                pdf.cell(w, 4.5, f"  {neg_line}",
                         new_x="LMARGIN", new_y="NEXT")
            pdf.ln(gap)

            # AI 인사이트
            if aff.ai_text:
                pdf.set_font(font, "", 8)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(w, 4, aff.ai_text)
                pdf.set_text_color(0, 0, 0)
                pdf.ln(gap)

        # ── 3. 차량 평가 ──
        veh = report.vehicle_evaluation
        if veh:
            self._section(pdf, font, "3. 차량 평가")

            # 호평 차량
            self._vehicle_list(pdf, font, w, "호평 차량", veh.top_liked or [], "호평률")

            # 불만 차량
            self._vehicle_list(pdf, font, w, "불만 차량", veh.top_disliked or [], "불만률")

            # AI 인사이트
            if veh.ai_text:
                pdf.set_font(font, "", 8)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(w, 4, veh.ai_text)
                pdf.set_text_color(0, 0, 0)
                pdf.ln(gap)

        # ── 4. 트렌드 비교 ──
        if report.trend_comparison:
            tc = report.trend_comparison
            self._section(pdf, font, "4. 트렌드 비교")

            pdf.set_font(font, "", 8)
            pdf.cell(w, row, f"이전 기간: {tc.previous_period} ({tc.previous_total_reviews}건)",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.cell(w, row, f"현재 기간: {tc.current_period} ({tc.current_total_reviews}건)",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.ln(gap)

            pos_sign = "+" if tc.overall_positive_change >= 0 else ""
            neg_sign = "+" if tc.overall_negative_change >= 0 else ""
            pdf.set_font(font, "B", 9)
            pdf.cell(w, row, f"긍정률 변화: {pos_sign}{tc.overall_positive_change}%p  |  부정률 변화: {neg_sign}{tc.overall_negative_change}%p",
                     new_x="LMARGIN", new_y="NEXT")
            pdf.ln(gap)

            if tc.category_trends:
                col_cat = 50
                col_prev = 30
                col_cur = 30
                col_chg = w - col_cat - col_prev - col_cur

                pdf.set_font(font, "B", 7)
                pdf.set_fill_color(240, 240, 240)
                pdf.cell(col_cat, row, " 카테고리", border=1, fill=True)
                pdf.cell(col_prev, row, " 이전", border=1, fill=True, align="C")
                pdf.cell(col_cur, row, " 현재", border=1, fill=True, align="C")
                pdf.cell(col_chg, row, " 변화", border=1, fill=True, align="C")
                pdf.ln(row)

                pdf.set_font(font, "", 7)
                for t in tc.category_trends:
                    arrow = "▲" if t.direction == "up" else ("▼" if t.direction == "down" else "-")
                    chg_sign = "+" if t.change >= 0 else ""
                    pdf.cell(col_cat, row, f" {t.category_name}", border=1)
                    pdf.cell(col_prev, row, f"{t.previous_ratio}%", border=1, align="C")
                    pdf.cell(col_cur, row, f"{t.current_ratio}%", border=1, align="C")
                    pdf.cell(col_chg, row, f"{arrow} {chg_sign}{t.change}%p", border=1, align="C")
                    pdf.ln(row)
            pdf.ln(gap)

        # ── 5. 벤치마크 ──
        if report.benchmark:
            bm = report.benchmark
            self._section(pdf, font, "5. 벤치마크")

            col_third = (w - 8) / 3
            pdf.set_font(font, "B", 8)
            pdf.cell(col_third, row, "이 지점", align="C")
            pdf.set_x(pdf.get_x() + 4)
            pdf.cell(col_third, row, f"{bm.region_name or '지역'} 평균", align="C")
            pdf.set_x(pdf.get_x() + 4)
            pdf.cell(col_third, row, "전국 평균", align="C")
            pdf.ln(row)

            pdf.set_font(font, "B", 12)
            pdf.cell(col_third, 7, f"{bm.branch_rating:.1f}", align="C")
            pdf.set_x(pdf.get_x() + 4)
            pdf.cell(col_third, 7, f"{bm.regional_avg_rating:.1f}", align="C")
            pdf.set_x(pdf.get_x() + 4)
            pdf.cell(col_third, 7, f"{bm.national_avg_rating:.1f}", align="C")
            pdf.ln(7)

            pdf.set_font(font, "", 7)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(col_third, row, "", align="C")
            pdf.set_x(pdf.get_x() + 4)
            pdf.cell(col_third, row, f"상위 {bm.regional_rank_pct}% ({bm.total_branches_in_region}개 지점)", align="C")
            pdf.set_x(pdf.get_x() + 4)
            pdf.cell(col_third, row, f"상위 {bm.national_rank_pct}% ({bm.total_branches_national}개 지점)", align="C")
            pdf.ln(row)
            pdf.set_text_color(0, 0, 0)

            if bm.branch_rating > 0:
                pdf.set_font(font, "", 8)
                if bm.branch_rating >= bm.regional_avg_rating:
                    msg = f"이 지점은 {bm.region_name or '해당 지역'} 평균 이상의 평점을 유지하고 있습니다."
                else:
                    msg = f"이 지점은 {bm.region_name or '해당 지역'} 평균보다 낮은 평점이므로, 개선 조치가 필요할 수 있습니다."
                pdf.multi_cell(w, row, msg)
            pdf.ln(gap)

        # ── 푸터 ──
        self._hr(pdf, m, w)
        pdf.set_font(font, "", 7)
        pdf.set_text_color(150, 150, 150)
        pdf.cell(w, 4, f"Carmore AI  |  {report.generated_at}", align="C")
        pdf.set_text_color(0, 0, 0)

        return bytes(pdf.output())

    # ── 심플 헬퍼 ──

    # 브랜드 접두사 (DB 원본에 "기아K5", "현대아반떼" 등으로 저장됨)
    _BRAND_PREFIXES = [
        "BMWBMW", "BMW",
        "벤츠", "아우디아우디", "아우디",
        "현대", "기아", "쉐보레", "르노", "쌍용",
    ]

    @classmethod
    def _clean_model(cls, raw: str) -> str:
        """브랜드 접두사를 분리하여 '브랜드 모델명' 형태로 변환"""
        for prefix in cls._BRAND_PREFIXES:
            if raw.startswith(prefix) and len(raw) > len(prefix):
                brand = prefix.replace("BMWBMW", "BMW").replace("아우디아우디", "아우디")
                rest = raw[len(prefix):].lstrip()
                return f"{brand} {rest}"
        return raw

    def _hr(self, pdf: FPDF, m: float, w: float) -> None:
        """수평 구분선"""
        pdf.ln(3)
        y = pdf.get_y()
        pdf.set_draw_color(200, 200, 200)
        pdf.line(m, y, m + w, y)
        pdf.ln(3)

    def _section(self, pdf: FPDF, font: str, title: str) -> None:
        """섹션 제목"""
        pdf.set_font(font, "B", 11)
        pdf.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    def _sub(self, pdf: FPDF, font: str, title: str) -> None:
        """서브 제목"""
        pdf.set_font(font, "B", 9)
        pdf.cell(0, 5, title, new_x="LMARGIN", new_y="NEXT")

    def _vehicle_list(
        self, pdf: FPDF, font: str, w: float,
        title: str, vehicles: list, ratio_label: str,
    ) -> None:
        """차량 리스트 (테이블 대신 한 줄씩 표시)"""
        if not vehicles:
            return

        h = 4.5
        self._sub(pdf, font, title)
        pdf.ln(1)

        for i, v in enumerate(vehicles[:5], 1):
            model = self._clean_model(v.model)
            tags_text = ", ".join(v.tags[:3]) if v.tags else ""
            tag_part = f"  {tags_text}" if tags_text else ""

            pdf.set_font(font, "", 8)
            pdf.cell(w, h,
                     f"  {i}. {model}{tag_part}",
                     new_x="LMARGIN", new_y="NEXT")

        pdf.ln(2)

    # ================================================================
    # 레거시 포맷 (하위호환)
    # ================================================================

    def _generate_legacy_format(self, report: ReportData) -> bytes:
        pdf, font = self._setup_pdf()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        pdf.set_font(font, "B", 16)
        pdf.cell(0, 10, f"{report.branch_name} AI 컨설팅 리포트",
                 align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        pdf.set_font(font, "", 10)
        pdf.cell(0, 6, f"분석 기간: {report.period_start} ~ {report.period_end}",
                 align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"총 리뷰 수: {report.total_reviews}건",
                 align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(8)

        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(8)

        w = 190

        pdf.set_font(font, "B", 12)
        pdf.cell(w, 8, "기간별 요약", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "", 10)
        pdf.multi_cell(w, 6, report.period_summary or "요약 없음")
        pdf.ln(6)

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

            pdf.set_font(font, "B", 9)
            pdf.cell(w, 6, f"  전체 차량 현황 ({len(vehicles)}대)",
                     new_x="LMARGIN", new_y="NEXT")
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

        pdf.ln(10)
        pdf.set_draw_color(200, 200, 200)
        pdf.line(10, pdf.get_y(), 200, pdf.get_y())
        pdf.ln(5)
        pdf.set_font(font, "", 8)
        pdf.cell(0, 5, f"Generated by Carmore AI  |  {report.generated_at}", align="C")

        return bytes(pdf.output())
