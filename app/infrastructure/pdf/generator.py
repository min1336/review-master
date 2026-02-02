"""
PDF 생성기

WeasyPrint를 사용하여 HTML 템플릿을 PDF로 변환합니다.
Jinja2 템플릿 엔진을 활용하여 HTML을 렌더링합니다.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from jinja2 import Environment, FileSystemLoader, select_autoescape

if TYPE_CHECKING:
    from services.report_service import ReportData


class PDFGenerator:
    """PDF 생성기"""

    def __init__(self):
        # 템플릿 디렉토리 설정 (app/templates)
        app_dir = Path(__file__).resolve().parent.parent.parent
        self.template_dir = app_dir / "templates"

        # Jinja2 환경 설정
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(self.template_dir)),
            autoescape=select_autoescape(["html", "xml"]),
        )

    def generate(self, report: ReportData) -> bytes:
        """
        리포트 데이터를 PDF로 변환

        Args:
            report: 리포트 데이터

        Returns:
            PDF 바이트 데이터
        """
        try:
            from weasyprint import HTML
        except ImportError:
            logging.warning("WeasyPrint not installed, using fallback PDF generation")
            return self._generate_fallback_pdf(report)

        # HTML 렌더링
        html_content = self._render_html(report)

        # PDF 생성
        html = HTML(string=html_content)
        pdf_bytes = html.write_pdf()

        return pdf_bytes

    def _render_html(self, report: ReportData) -> str:
        """Jinja2 템플릿을 사용한 HTML 렌더링"""
        template = self._jinja_env.get_template("pdf/report_template.html")
        return template.render(report=report)

    def _generate_fallback_pdf(self, report: ReportData) -> bytes:
        """WeasyPrint 없을 때 대체 PDF 생성 (reportlab 사용)"""
        try:
            import io

            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.platypus import (
                Paragraph,
                SimpleDocTemplate,
                Spacer,
                Table,
                TableStyle,
            )

            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4)
            styles = getSampleStyleSheet()
            story = []

            # 제목
            title_style = ParagraphStyle(
                'Title',
                parent=styles['Heading1'],
                fontSize=18,
                alignment=1,
            )
            story.append(
                Paragraph(f"{report.branch_name} AI Report", title_style)
            )
            story.append(Spacer(1, 12))
            period_text = f"Period: {report.period_start} ~ {report.period_end}"
            story.append(Paragraph(period_text, styles['Normal']))
            story.append(Spacer(1, 24))

            # 요약
            story.append(Paragraph("Summary", styles['Heading2']))
            summary_text = report.period_summary or "No summary available."
            story.append(Paragraph(summary_text, styles['Normal']))
            story.append(Spacer(1, 12))

            # 통계
            stats_data = [
                ['Total Reviews', 'Strengths', 'Weaknesses', 'Actions'],
                [
                    str(report.total_reviews),
                    str(len(report.strengths)),
                    str(len(report.weaknesses)),
                    str(len(report.action_items)),
                ],
            ]
            stats_table = Table(stats_data)
            stats_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
            ]))
            story.append(stats_table)

            doc.build(story)
            return buffer.getvalue()

        except ImportError as e:
            # 아무 라이브러리도 없으면 에러 발생
            logging.error("No PDF library available")
            raise RuntimeError(
                "PDF generation not available. "
                "Install weasyprint or reportlab."
            ) from e
