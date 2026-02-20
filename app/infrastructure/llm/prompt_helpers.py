"""프롬프트 공통 유틸리티

affiliate/vehicle 평가 프롬프트에서 공유하는 태그 포맷팅 로직.
"""

from __future__ import annotations


def compute_ratio(numerator: int, total: int) -> int:
    """비율 계산 (0 나눗셈 안전)"""
    return round(numerator / total * 100) if total > 0 else 0


def format_tag_stats_lines(tag_details: list[dict]) -> str:
    """태그 통계 → 프롬프트용 텍스트 (affiliate/vehicle 공통)

    Args:
        tag_details: [{"tag_name": str, "positive": int, "negative": int, "total": int}]

    Returns:
        포맷된 태그 통계 텍스트 (빈 경우 "  데이터 없음")
    """
    lines: list[str] = []
    for t in tag_details:
        name = t.get("tag_name", "")
        pos = t.get("positive", 0)
        neg = t.get("negative", 0)
        total = t.get("total", 0)
        if total == 0:
            continue
        pos_ratio = compute_ratio(pos, total)
        neg_ratio = compute_ratio(neg, total)
        if neg_ratio > pos_ratio:
            lines.append(f"  {name}(부정 {neg}건/{total}건)")
        else:
            lines.append(f"  {name}(긍정 {pos}건/{total}건)")
    return "\n".join(lines) if lines else "  데이터 없음"
