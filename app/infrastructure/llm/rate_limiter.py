"""
Rate Limiter
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    분당 요청 수(RPM) 제한을 위한 Rate Limiter (스레드 안전)

    Usage:
        limiter = RateLimiter(rpm=60)
        limiter.wait_if_needed()  # 필요시 대기
        # API 호출
    """

    def __init__(self, rpm: int = 60):
        """
        Args:
            rpm: 분당 최대 요청 수
        """
        self.rpm = rpm
        self.min_interval = 60.0 / rpm
        self.last_request_time = 0
        self.request_count = 0
        self.window_start = time.time()
        self._lock = threading.Lock()

    def wait_if_needed(self):
        """필요시 대기하여 Rate Limit 준수 (스레드 안전, 락 밖에서 sleep)"""
        sleep_time = 0.0

        with self._lock:
            current_time = time.time()

            # 1분 윈도우 리셋
            if current_time - self.window_start >= 60:
                self.window_start = current_time
                self.request_count = 0

            # 분당 요청 수 초과 시 대기 시간 계산
            if self.request_count >= self.rpm:
                wait_time = 60 - (current_time - self.window_start)
                if wait_time > 0:
                    sleep_time = wait_time

            # 요청 간 최소 간격 유지
            if sleep_time == 0:
                elapsed = current_time - self.last_request_time
                if elapsed < self.min_interval:
                    sleep_time = self.min_interval - elapsed

        # 락 해제 후 대기 (다른 스레드 블로킹 방지)
        if sleep_time > 0:
            if sleep_time > 1:
                logger.warning("Rate limit 도달, %.1f초 대기...", sleep_time)
            time.sleep(sleep_time)

        # 대기 후 요청 기록
        with self._lock:
            now = time.time()
            if now - self.window_start >= 60:
                self.window_start = now
                self.request_count = 0
            self.last_request_time = now
            self.request_count += 1

