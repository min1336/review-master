"""
Rate Limiter
"""
import time


class RateLimiter:
    """
    분당 요청 수(RPM) 제한을 위한 Rate Limiter

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

    def wait_if_needed(self):
        """필요시 대기하여 Rate Limit 준수"""
        current_time = time.time()

        # 1분 윈도우 리셋
        if current_time - self.window_start >= 60:
            self.window_start = current_time
            self.request_count = 0

        # 분당 요청 수 초과 시 대기
        if self.request_count >= self.rpm:
            wait_time = 60 - (current_time - self.window_start)
            if wait_time > 0:
                print(f"  ⏳ Rate limit 도달, {wait_time:.1f}초 대기...")
                time.sleep(wait_time)
                self.window_start = time.time()
                self.request_count = 0

        # 요청 간 최소 간격 유지
        elapsed = current_time - self.last_request_time
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)

        self.last_request_time = time.time()
        self.request_count += 1

    def reset(self):
        """리셋"""
        self.last_request_time = 0
        self.request_count = 0
        self.window_start = time.time()
