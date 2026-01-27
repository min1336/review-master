from __future__ import annotations

import re

# 금지어 목록
FORBIDDEN_WORDS = [
    "최고",
    "완벽",
    "강력추천",
    "무조건",
    "대박",
    "짱",
    "굿",
    "베스트",
    "넘버원",
]

# 검증 기준 (v2.0 업데이트)
MIN_CHAR_COUNT = 100  # 최소 글자 수
MAX_CHAR_COUNT = 350  # 최대 글자 수 (좋은점 220자 + 아쉬운점 80자 + 여유)
MIN_SENTENCES = 3  # 최소 문장 수
MAX_SENTENCES = 8  # 최대 문장 수


def validate_summary(text: str) -> tuple[bool, list[str]]:
    """
    요약 출력 검증

    Args:
        text: 검증할 요약 텍스트

    Returns:
        Tuple[bool, List[str]]: (통과 여부, 오류 목록)
    """
    if not text or not text.strip():
        return False, ["빈 텍스트"]

    errors = []
    text = text.strip()

    # 1. 문장 수 체크 (마침표 기준) - 범위 허용
    sentences = _count_sentences(text)
    if sentences < MIN_SENTENCES:
        errors.append(f"문장 수 부족: {sentences}개 (최소 {MIN_SENTENCES}개)")
    elif sentences > MAX_SENTENCES:
        errors.append(f"문장 수 초과: {sentences}개 (최대 {MAX_SENTENCES}개)")

    # 2. 글자 수 체크
    char_count = len(text)
    if char_count < MIN_CHAR_COUNT:
        errors.append(f"글자 수 부족: {char_count}자 (최소 {MIN_CHAR_COUNT}자)")
    elif char_count > MAX_CHAR_COUNT:
        errors.append(f"글자 수 초과: {char_count}자 (최대 {MAX_CHAR_COUNT}자)")

    # 3. 금지어 체크
    found_forbidden = _check_forbidden_words(text)
    if found_forbidden:
        errors.append(f"금지어 포함: {', '.join(found_forbidden)}")

    # 4. 마크다운/이모지 체크
    if _has_markdown_or_emoji(text):
        errors.append("마크다운 또는 이모지 포함")

    return len(errors) == 0, errors


def _count_sentences(text: str) -> int:
    """마침표 기준 문장 수 카운트"""
    # 마침표로 끝나는 문장 카운트
    sentences = [s.strip() for s in text.split(".") if s.strip()]
    return len(sentences)


def _check_forbidden_words(text: str) -> list[str]:
    """금지어 포함 여부 체크"""
    found = []
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in text_lower:
            found.append(word)
    return found


def _has_markdown_or_emoji(text: str) -> bool:
    """마크다운 또는 이모지 포함 여부"""
    # 마크다운 패턴 (엄격하게)
    markdown_patterns = [
        r"\*\*[^*]+\*\*",  # bold: **text**
        r"__[^_]+__",  # bold: __text__
        r"(?<!\w)\*[^*]+\*(?!\w)",  # italic: *text* (단어 경계)
        r"#+\s+\w",  # heading: # text
        r"\[.+\]\(.+\)",  # link: [text](url)
        r"`[^`]+`",  # code: `code`
        r"^\s*[-*•]\s+",  # bullet list (-, *, •)
        # r'^\s*\d+\.\s+',   # numbered list - 문단에서 숫자 사용 가능하므로 허용
    ]

    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE):
            return True

    # 이모지 체크 (정확한 유니코드 이모지 범위만)
    emoji_pattern = re.compile(
        "["
        "\U0001f600-\U0001f64f"  # emoticons (smileys)
        "\U0001f300-\U0001f5ff"  # symbols & pictographs
        "\U0001f680-\U0001f6ff"  # transport & map
        "\U0001f1e0-\U0001f1ff"  # flags
        "\U0001f900-\U0001f9ff"  # supplemental symbols
        "\U0001fa00-\U0001fa6f"  # chess symbols
        "\U0001fa70-\U0001faff"  # symbols extended-A
        "\U00002600-\U000026ff"  # misc symbols (sun, moon, etc.)
        "\U00002700-\U000027bf"  # dingbats (arrows, etc.)
        "]+",
        flags=re.UNICODE,
    )

    return bool(emoji_pattern.search(text))


def validate_and_log(text: str, branch_name: str = None) -> tuple[bool, str]:
    """
    검증 및 로그용 결과 반환

    Args:
        text: 검증할 텍스트
        branch_name: 지점명 (로그용)

    Returns:
        Tuple[bool, str]: (통과 여부, 로그 메시지)
    """
    is_valid, errors = validate_summary(text)

    if is_valid:
        msg = f"[{branch_name or '지점'}] 검증 통과"
    else:
        msg = f"[{branch_name or '지점'}] 검증 실패: {'; '.join(errors)}"

    return is_valid, msg
