"""Playwright E2E: 수동 동기화 UI 흐름 검증 (V-004)

검증 항목:
1. analysis 페이지 로드 성공
2. btn-manual-sync 버튼 존재 및 클릭 가능
3. 클릭 후 sync-progress-overlay 표시
4. 서버 응답 후 오버레이 사라지거나 에러 메시지 표시 (무한 로딩 아님)
"""

from __future__ import annotations

import socket

import pytest
from playwright.sync_api import sync_playwright, expect

BASE_URL = "http://127.0.0.1:18765"


def _server_reachable() -> bool:
    """BASE_URL 서버에 TCP 연결 가능한지 확인"""
    try:
        with socket.create_connection(("127.0.0.1", 18765), timeout=1):
            return True
    except OSError:
        return False


_skip_no_server = pytest.mark.skipif(
    not _server_reachable(),
    reason=f"서버 미실행 ({BASE_URL})",
)


@_skip_no_server
def test_analysis_page_loads():
    """analysis 페이지가 정상 로드되는지 확인"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        response = page.goto(f"{BASE_URL}/analysis", wait_until="domcontentloaded")
        assert response.status == 200, f"페이지 로드 실패: {response.status}"

        # 페이지 제목 확인
        title = page.locator("header h1")
        expect(title).to_have_text("리뷰 분석")

        browser.close()


@_skip_no_server
def test_manual_sync_button_exists():
    """btn-manual-sync 버튼이 존재하고 클릭 가능한지 확인"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/analysis", wait_until="domcontentloaded")

        btn = page.locator("#btn-manual-sync")
        expect(btn).to_be_visible()
        expect(btn).to_be_enabled()
        expect(btn).to_contain_text("수동 동기화")

        browser.close()


@_skip_no_server
def test_sync_click_shows_overlay_then_resolves():
    """수동 동기화 클릭 → 오버레이 표시 → 무한 로딩 없이 해소됨"""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(f"{BASE_URL}/analysis", wait_until="domcontentloaded")

        btn = page.locator("#btn-manual-sync")
        btn.click()

        # 1. 프로그레스 오버레이가 표시되어야 함
        overlay = page.locator("#sync-progress-overlay")
        expect(overlay).to_be_visible(timeout=5000)

        # 2. 15초 내에 오버레이가 사라지거나 에러 토스트가 나와야 함
        #    (무한 로딩이 아님을 증명)
        #    - 오버레이가 사라짐 = 동기화 완료/실패 처리됨
        #    - 또는 토스트 에러 메시지가 표시됨
        try:
            overlay.wait_for(state="hidden", timeout=15000)
            overlay_resolved = True
        except Exception:
            overlay_resolved = False

        if not overlay_resolved:
            # 오버레이가 아직 있으면, 취소 버튼이 작동하는지 확인
            cancel_btn = page.locator("#sync-cancel-btn")
            if cancel_btn.is_visible():
                cancel_btn.click()
                # 취소 후에는 오버레이가 사라져야 함
                overlay.wait_for(state="hidden", timeout=5000)

        # 3. 버튼이 다시 활성화되어야 함 (무한 disabled 상태 아님)
        expect(btn).to_be_enabled(timeout=5000)

        # 4. syncing 클래스가 제거되어야 함
        expect(btn).not_to_have_class("syncing", timeout=5000)

        browser.close()
