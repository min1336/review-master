"""
LLM 출력 검증기
- 문장 수 검증
- 글자 수 검증
- 금지어 검증
"""
from typing import Tuple, List
import re


# 금지어 목록
FORBIDDEN_WORDS = [
    '최고', '완벽', '강력추천', '무조건', '대박',
    '짱', '굿', '베스트', '넘버원'
]

# 검증 기준
MIN_CHAR_COUNT = 60   # 최소 글자 수
MAX_CHAR_COUNT = 200  # 최대 글자 수
EXPECTED_SENTENCES = 3  # 기대 문장 수


def validate_summary(text: str) -> Tuple[bool, List[str]]:
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

    # 1. 문장 수 체크 (마침표 기준)
    sentences = _count_sentences(text)
    if sentences != EXPECTED_SENTENCES:
        errors.append(f"문장 수 오류: {sentences}개 (3개 필요)")

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
    sentences = [s.strip() for s in text.split('.') if s.strip()]
    return len(sentences)


def _check_forbidden_words(text: str) -> List[str]:
    """금지어 포함 여부 체크"""
    found = []
    text_lower = text.lower()
    for word in FORBIDDEN_WORDS:
        if word in text_lower:
            found.append(word)
    return found


def _has_markdown_or_emoji(text: str) -> bool:
    """마크다운 또는 이모지 포함 여부"""
    # 마크다운 패턴 (더 엄격하게)
    markdown_patterns = [
        r'\*\*[^*]+\*\*',   # bold: **text**
        r'__[^_]+__',        # bold: __text__
        r'(?<!\w)\*[^*]+\*(?!\w)',  # italic: *text* (단어 경계)
        r'#+\s+\w',          # heading: # text
        r'\[.+\]\(.+\)',     # link: [text](url)
        r'`[^`]+`',          # code: `code`
        r'^\s*[-*]\s+',      # bullet list
        r'^\s*\d+\.\s+',     # numbered list
    ]

    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE):
            return True

    # 이모지 체크 (정확한 유니코드 이모지 범위만)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons (smileys)
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U0001F900-\U0001F9FF"  # supplemental symbols
        "\U0001FA00-\U0001FA6F"  # chess symbols
        "\U0001FA70-\U0001FAFF"  # symbols extended-A
        "\U00002600-\U000026FF"  # misc symbols (sun, moon, etc.)
        "\U00002700-\U000027BF"  # dingbats (arrows, etc.)
        "]+",
        flags=re.UNICODE
    )

    return bool(emoji_pattern.search(text))


def validate_and_log(text: str, branch_name: str = None) -> Tuple[bool, str]:
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
