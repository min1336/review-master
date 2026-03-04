"""
TZ-Aware JSON Response 모듈

naive datetime에 자동으로 UTC offset을 부착하여
모든 API 응답에서 datetime이 항상 offset을 포함하도록 보장한다.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fastapi.responses import JSONResponse


class _TZAwareEncoder(json.JSONEncoder):
    """naive datetime에 자동으로 +00:00 offset을 부착하는 인코더."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            if obj.tzinfo is None:
                from core.timezone import UTC

                obj = obj.replace(tzinfo=UTC)
            return obj.isoformat()
        return super().default(obj)


class TZAwareJSONResponse(JSONResponse):
    """모든 API 응답에서 datetime이 항상 offset을 포함하도록 보장."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content,
            cls=_TZAwareEncoder,
            ensure_ascii=False,
        ).encode("utf-8")
