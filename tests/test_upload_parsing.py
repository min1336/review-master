"""업로드 파싱 및 컬럼 매핑 유닛 테스트

DB/외부 서비스 의존성 없이, 파일 파싱 + 한글→영문 매핑 로직만 검증한다.
"""

from __future__ import annotations

import csv
import io


def _make_csv_bytes(rows: list[dict]) -> bytes:
    """딕셔너리 리스트 → CSV 바이트"""
    if not rows:
        return b""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=rows[0].keys())
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8-sig")


class TestParseCsvContent:
    def test_basic_csv(self):
        from services.upload_job_service import parse_csv_content

        rows = [
            {"리뷰번호": "1", "지점번호": "100", "리뷰내용": "좋아요"},
            {"리뷰번호": "2", "지점번호": "200", "리뷰내용": "별로"},
        ]
        content = _make_csv_bytes(rows)
        result = parse_csv_content(content)

        assert len(result) == 2
        assert result[0]["리뷰번호"] == "1"
        assert result[1]["리뷰내용"] == "별로"

    def test_empty_csv(self):
        from services.upload_job_service import parse_csv_content

        content = b""
        result = parse_csv_content(content)
        assert result == []


class TestParseExcelContent:
    def test_basic_excel(self):
        from openpyxl import Workbook
        from services.upload_job_service import parse_excel_content

        wb = Workbook()
        ws = wb.active
        ws.append(["리뷰번호", "지점번호", "리뷰내용"])
        ws.append(["1", "100", "좋아요"])
        ws.append(["2", "200", "별로"])

        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()

        result = parse_excel_content(content)
        assert len(result) == 2
        assert result[0]["리뷰번호"] == "1"
        assert result[1]["리뷰내용"] == "별로"

    def test_empty_excel(self):
        from openpyxl import Workbook
        from services.upload_job_service import parse_excel_content

        wb = Workbook()
        buf = io.BytesIO()
        wb.save(buf)
        content = buf.getvalue()

        result = parse_excel_content(content)
        # 빈 시트에 헤더만 없으므로 빈 리스트
        assert result == []


class TestValidateColumns:
    def test_korean_columns_pass(self):
        from services.upload_job_service import validate_columns

        rows = [{"리뷰번호": "1", "지점번호": "100", "리뷰내용": "ok"}]
        assert validate_columns(rows) is None

    def test_english_columns_pass(self):
        from services.upload_job_service import validate_columns

        rows = [{"review_id": "1", "branch_id": "100", "content": "ok"}]
        assert validate_columns(rows) is None

    def test_missing_columns_fail(self):
        from services.upload_job_service import validate_columns

        rows = [{"이름": "홍길동", "내용": "리뷰"}]
        error = validate_columns(rows)
        assert error is not None
        assert "필수 컬럼 누락" in error

    def test_empty_data_fail(self):
        from services.upload_job_service import validate_columns

        error = validate_columns([])
        assert error is not None
        assert "데이터가 없습니다" in error


class TestParseRows:
    def test_korean_headers_mapping(self):
        from services.upload_job_service import parse_rows

        raw_dicts = [
            {
                "리뷰번호": "123",
                "지점번호": "456",
                "리뷰내용": "<br>좋은 서비스</br>",
                "예약_지점명": "제주점",
                "예약_업체명": "카모어",
                "지점평점(친절/편의성)": "4.5",
                "차량평점": "4.0",
                "인수/반납편의성": "3.5",
                "도움돼요수": "10",
                "등록일시": "2026-01-15",
                "리뷰상태": "정상",
                "차량모델": "소형",
                "렌트타입": "SHORT",
            }
        ]

        raw_rows, mapped_rows, errors = parse_rows(raw_dicts)

        assert len(raw_rows) == 1
        assert len(mapped_rows) == 1
        assert len(errors) == 0

        m = mapped_rows[0]
        assert m["review_id"] == "123"
        assert m["branch_id"] == "456"
        assert "좋은 서비스" in m["content"]
        assert "<br>" not in m["content"]  # HTML 태그 제거
        assert m["branch_name"] == "제주점"
        assert m["status"] == "normal"  # 정상 → normal 매핑
        assert m["car_type"] == "소형"

        # raw_rows에 is_new=True 추가됨
        assert raw_rows[0]["is_new"] is True

    def test_english_headers_passthrough(self):
        from services.upload_job_service import parse_rows

        raw_dicts = [
            {
                "review_id": "789",
                "branch_id": "101",
                "content": "Great <b>service</b>",
                "rating_service": "5.0",
            }
        ]

        raw_rows, mapped_rows, errors = parse_rows(raw_dicts)
        assert len(raw_rows) == 1
        assert len(mapped_rows) == 1
        assert "Great" in mapped_rows[0]["content"]
        assert "<b>" not in mapped_rows[0]["content"]

    def test_missing_review_id_error(self):
        from services.upload_job_service import parse_rows

        raw_dicts = [
            {"리뷰번호": "", "지점번호": "100"},
        ]

        raw_rows, mapped_rows, errors = parse_rows(raw_dicts)
        assert len(raw_rows) == 0
        assert len(errors) == 1
        assert "review_id" in errors[0].error

    def test_missing_branch_id_error(self):
        from services.upload_job_service import parse_rows

        raw_dicts = [
            {"리뷰번호": "123", "지점번호": ""},
        ]

        raw_rows, mapped_rows, errors = parse_rows(raw_dicts)
        assert len(raw_rows) == 0
        assert len(errors) == 1
        assert "branch_id" in errors[0].error

    def test_mixed_valid_invalid(self):
        from services.upload_job_service import parse_rows

        raw_dicts = [
            {"리뷰번호": "1", "지점번호": "100", "리뷰내용": "좋아요"},
            {"리뷰번호": "", "지점번호": "200", "리뷰내용": "빈 ID"},
            {"리뷰번호": "3", "지점번호": "300", "리뷰내용": "괜찮아요"},
        ]

        raw_rows, mapped_rows, errors = parse_rows(raw_dicts)
        assert len(raw_rows) == 2
        assert len(mapped_rows) == 2
        assert len(errors) == 1


class TestStripHtml:
    def test_html_tags_removed(self):
        from services.upload_job_service import _strip_html

        assert _strip_html("<br>안녕<br/>하세요</p>") == "안녕 하세요"

    def test_null_bytes_removed(self):
        from services.upload_job_service import _strip_html

        assert "\x00" not in _strip_html("hello\x00world")

    def test_empty_string(self):
        from services.upload_job_service import _strip_html

        assert _strip_html("") == ""
        assert _strip_html(None) == ""


class TestStripNull:
    def test_removes_null_bytes(self):
        from services.upload_job_service import _strip_null

        assert _strip_null("hello\x00world") == "helloworld"

    def test_empty_string(self):
        from services.upload_job_service import _strip_null

        assert _strip_null("") == ""


class TestUploadSchemas:
    def test_job_status_serialization(self):
        from schemas.jobs import UploadJobStatusResponse

        resp = UploadJobStatusResponse(
            job_id="abc123",
            status="completed",
            progress=100,
            message="완료",
            total_rows=50,
        )
        data = resp.model_dump(mode="json")
        assert data["job_id"] == "abc123"
        assert data["status"] == "completed"
        assert data["progress"] == 100

    def test_result_response_serialization(self):
        from schemas.jobs import UploadResultResponse, UploadRowError

        resp = UploadResultResponse(
            success=True,
            uploaded_count=100,
            upserted_count=98,
            processed_count=95,
            failed_count=3,
            duration_seconds=12.5,
            errors=[UploadRowError(row=5, error="test error")],
        )
        data = resp.model_dump(mode="json")
        assert data["uploaded_count"] == 100
        assert len(data["errors"]) == 1
        assert data["errors"][0]["row"] == 5
