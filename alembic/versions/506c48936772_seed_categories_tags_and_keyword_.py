"""seed categories tags and keyword mappings

Revision ID: 506c48936772
Revises: a9b915291736
Create Date: 2026-04-03 11:30:52.754101

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '506c48936772'
down_revision: Union[str, None] = 'a9b915291736'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── TAG_REGISTRY 미러 (patterns.py 기준) ────────────────────────
# (category_name, group, color, description, positive_label, negative_label, display_order)
CATEGORIES = [
    ("직원친절", "affiliate", "#10b981", "직원 친절 응대 서비스 태도", "직원이 친절함", "직원이 불친절함", 1),
    ("외관", "vehicle", "#3b82f6", "차량 외관 외형 성능 옵션", "차량외관이 좋음", "차량외관이 별로임", 2),
    ("가격", "affiliate", "#8b5cf6", "가격 요금 할인 가성비", "가격이 저렴함", "가격이 비쌈", 3),
    ("청결", "vehicle", "#0ea5e9", "청결 청소 냄새 실내 세차", "차량이 청결함", "차량이 더러움", 4),
    ("사고 처리", "affiliate", "#ef4444", "사고 보험 보장 면책 수리", "사고 처리를 잘해줌", "사고 처리가 별로임", 5),
    ("주유비", "affiliate", "#f59e0b", "주유 연료 연비 충전", "주유비 부담 없음", "주유비 부담 높음", 6),
    ("배달/배차", "affiliate", "#06b6d4", "딜리버리 배차 배달 탁송", "배달/배차가 우수함", "배달/배차가 별로임", 7),
    ("반납/픽업", "affiliate", "#14b8a6", "반납 픽업 인수 반환", "반납/픽업이 원활함", "반납/픽업이 불편함", 8),
    ("위치/접근성", "affiliate", "#a855f7", "공항 역 위치 접근성 주차", "위치/접근성이 좋음", "위치/접근성이 불편함", 9),
]

# (tag_name, category_name, keywords)
TAGS = [
    # ── 직원친절 ──
    ("친절", "직원친절", ["친절", "불친절", "상냥", "배려", "미소", "배웅", "표정", "인사", "다정", "감사합니다", "고맙", "웃으며", "반갑", "환대", "갓서비스"]),
    ("안내", "직원친절", ["안내", "가이드"]),
    ("설명", "직원친절", ["설명"]),
    ("서비스", "직원친절", []),
    ("고객응대", "직원친절", ["응대", "고객", "태도", "말투", "무례", "무뚝뚝", "직원", "사장", "사장님", "알바", "스태프", "상담", "대응", "민원", "문의", "답변", "피드백", "관심", "케어", "불성실", "무성의", "거부"]),
    ("응대속도", "직원친절", ["빠른응대", "즉각", "신속응대"]),
    ("전화응대", "직원친절", ["전화", "콜센터", "통화"]),
    ("예약", "직원친절", ["예약"]),
    # ── 외관 ──
    ("외관", "외관", ["외관", "외부", "외형", "도색", "페인트", "광택", "깔끔한", "반짝", "멋진", "예쁜", "좋아보", "겉", "바디"]),
    ("차량외관", "외관", ["스크래치", "흠집", "긁힘", "찌그러짐", "찍힘", "긁힌", "움푹", "깨진", "금간", "범퍼", "휠", "바퀴", "유리", "창문", "와이퍼", "미러", "사이드미러", "타이어", "빵꾸", "펑크"]),
    ("신차", "외관", ["신차", "새차"]),
    ("연식", "외관", ["연식", "오래된", "낡은", "노후", "구형", "주행거리"]),
    ("성능", "외관", ["성능", "엔진", "시동", "브레이크", "제동", "핸들", "서스펜션", "떨림", "소음"]),
    ("옵션", "외관", ["에어컨", "히터", "후방카메라", "열선", "통풍시트"]),
    ("차종", "외관", ["차종"]),
    ("내비게이션", "외관", ["네비게이션", "네비", "내비"]),
    ("블랙박스", "외관", ["블랙박스"]),
    # ── 가격 ──
    ("가격", "가격", ["가격", "비싸", "비싼", "저렴", "싼", "합리", "돈", "비용", "금액", "착하", "부담없", "무료", "공짜", "경제적", "실속", "싸", "적정", "갓성비", "가심비"]),
    ("가성비", "가격", ["가성비"]),
    ("할인", "가격", ["할인", "혜택", "쿠폰", "이벤트", "프로모션"]),
    ("요금", "가격", ["요금", "렌트비"]),
    ("추가요금", "가격", ["추가비용", "추가금", "추가요금", "수수료", "폭리", "바가지", "호구", "호갱", "부담금", "눈탱이"]),
    ("정산", "가격", ["정산", "결제", "카드"]),
    ("면책금", "가격", ["면책금", "자기부담금"]),
    ("보험료", "가격", ["보험료"]),
    # ── 청결 ──
    ("청결", "청결", ["청결", "청소", "깨끗", "지저분", "더럽", "더러", "드러", "드럽", "위생", "오염", "깔끔", "정돈", "정리", "쓸었", "닦", "윤기", "개깔끔", "존좋"]),
    ("차량청결", "청결", ["이물질", "머리카락", "공기"]),
    ("세차", "청결", ["세차"]),
    ("냄새", "청결", ["냄새", "담배", "악취", "담배냄새", "곰팡이", "퀴퀴", "쩔어", "에어컨냄새", "냄새나", "곰팡이냄새", "담배흔적", "꿉꿉한"]),
    ("실내", "청결", ["실내", "내부", "바닥", "매트", "공간", "넓어", "쾌적"]),
    ("시트", "청결", ["시트", "좌석", "얼룩", "때", "먼지"]),
    ("트렁크", "청결", ["트렁크", "쓰레기"]),
    # ── 사고 처리 ──
    ("보험/보장", "사고 처리", ["보험", "보장", "완전자차", "자차", "대인", "대물", "대인대물", "종합보험", "책임보험", "자차보험", "커버", "풀커버", "안심보험", "완전면책"]),
    ("면책", "사고 처리", ["면책", "슈퍼면책", "자기부담", "슈퍼"]),
    ("사고처리", "사고 처리", ["사고", "사고접수", "사고처리"]),
    ("수리", "사고 처리", ["수리", "수리비", "파손", "충돌", "긁", "부딪"]),
    ("보상", "사고 처리", ["보상", "손해", "배상"]),
    ("긴급출동", "사고 처리", ["긴급출동", "출동", "견인", "로드서비스"]),
    ("대차", "사고 처리", ["대차", "대체차량"]),
    # ── 주유비 ──
    ("주유", "주유비", ["주유", "주유소", "주유량", "연료", "기름", "기름값", "연료비", "반납시주유", "휘발유", "경유", "가솔린", "디젤"]),
    ("연비", "주유비", ["연비", "기름값", "연료효율", "절약"]),
    ("충전", "주유비", ["충전", "충전소"]),
    ("전기차", "주유비", ["전기차", "전기"]),
    ("만탄", "주유비", ["만땅", "만탄"]),
    # ── 배달/배차 ──
    ("딜리버리", "배달/배차", ["딜리버리", "배달", "배송"]),
    ("배차/시간", "배달/배차", ["배차", "배정", "차량변경", "차종변경", "지연", "늦게", "늦음", "늦었", "기다림", "기다리", "재촉", "독촉", "급하", "빨리빨리", "서두르", "약속시간", "예약시간", "출발시간", "도착시간", "노쇼", "취소", "정시", "시간맞춰", "빠른배차", "차종", "대차", "시간약속", "예약취소"]),
    ("대기시간", "배달/배차", ["대기", "대기시간"]),
    ("탁송", "배달/배차", ["탁송"]),
    # ── 반납/픽업 ──
    ("반납/픽업", "반납/픽업", ["반납", "픽업", "인수", "수령", "전달", "인계", "반환", "차량인도", "출차", "입차"]),
    # ── 위치/접근성 ──
    ("위치/접근성", "위치/접근성", ["위치", "접근성", "역", "터미널"]),
    ("공항", "위치/접근성", ["공항"]),
    ("주차장", "위치/접근성", ["주차장", "주차", "무료주차", "유료주차"]),
]


def upgrade() -> None:
    conn = op.get_bind()

    # ── 1. categories ──
    cat_table = sa.table(
        "categories",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("color", sa.String),
        sa.column("display_order", sa.Integer),
        sa.column("is_active", sa.Boolean),
    )
    for name, _group, color, desc, _pos, _neg, order in CATEGORIES:
        conn.execute(
            cat_table.insert().values(
                name=name, description=desc, color=color,
                display_order=order, is_active=True,
            )
        )

    # category_name → id 매핑 구축
    rows = conn.execute(sa.text("SELECT id, name FROM categories")).fetchall()
    cat_id_map = {r[1]: r[0] for r in rows}

    # ── 2. tags (52개 + "일반" fallback) ──
    tag_table = sa.table(
        "tags",
        sa.column("id", sa.Integer),
        sa.column("name", sa.String),
        sa.column("group_name", sa.String),
        sa.column("category_id", sa.Integer),
        sa.column("color", sa.String),
        sa.column("sentiment", sa.String),
        sa.column("tag_type", sa.String),
        sa.column("is_active", sa.Boolean),
        sa.column("usage_count", sa.Integer),
    )

    # category → (group, color) 조회용
    cat_meta = {name: (group, color) for name, group, color, *_ in CATEGORIES}

    for tag_name, cat_name, _keywords in TAGS:
        group, color = cat_meta[cat_name]
        conn.execute(
            tag_table.insert().values(
                name=tag_name,
                group_name=group,
                category_id=cat_id_map[cat_name],
                color=color,
                sentiment="positive",
                tag_type="aspect",
                is_active=True,
                usage_count=0,
            )
        )

    # "일반" fallback 태그 (반납/픽업 카테고리 소속)
    conn.execute(
        tag_table.insert().values(
            name="일반",
            group_name="affiliate",
            category_id=cat_id_map["반납/픽업"],
            color="#9ca3af",
            sentiment="positive",
            tag_type="fallback",
            is_active=True,
            usage_count=0,
        )
    )

    # tag_name → id 매핑 구축
    rows = conn.execute(sa.text("SELECT id, name FROM tags")).fetchall()
    tag_id_map = {r[1]: r[0] for r in rows}

    # ── 3. keyword_mappings ──
    kw_table = sa.table(
        "keyword_mappings",
        sa.column("keyword", sa.Text),
        sa.column("tag_id", sa.Integer),
        sa.column("is_auto", sa.Boolean),
        sa.column("confidence", sa.Float),
    )

    seen_keywords: set[str] = set()
    for tag_name, _cat_name, keywords in TAGS:
        tid = tag_id_map[tag_name]
        for kw in keywords:
            if kw in seen_keywords:
                continue
            seen_keywords.add(kw)
            conn.execute(
                kw_table.insert().values(
                    keyword=kw, tag_id=tid, is_auto=False, confidence=1.0,
                )
            )


def downgrade() -> None:
    op.execute("DELETE FROM keyword_mappings")
    op.execute("DELETE FROM tags")
    op.execute("DELETE FROM categories")
