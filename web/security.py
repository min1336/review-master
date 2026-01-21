"""
IP 화이트리스트 보안 미들웨어

모든 API 엔드포인트에 대해 허용된 IP만 접근 가능하도록 제어
"""
import ipaddress
import os
import logging

from flask import request, abort, current_app
from werkzeug.middleware.proxy_fix import ProxyFix


logger = logging.getLogger(__name__)

# 기본 허용 IP (localhost)
DEFAULT_WHITELIST = ["127.0.0.1", "::1"]


def parse_ip_whitelist(whitelist_str: str) -> list:
    """
    쉼표로 구분된 IP 문자열을 파싱하여 IP 네트워크 객체 리스트 반환

    지원 형식:
    - 단일 IP: 192.168.1.100
    - CIDR: 192.168.1.0/24
    - IPv6: ::1, 2001:db8::/32
    """
    if not whitelist_str:
        return []

    networks = []
    for ip_str in whitelist_str.split(","):
        ip_str = ip_str.strip()
        if not ip_str:
            continue
        try:
            if "/" in ip_str:
                networks.append(ipaddress.ip_network(ip_str, strict=False))
            else:
                ip = ipaddress.ip_address(ip_str)
                prefix = 32 if ip.version == 4 else 128
                networks.append(ipaddress.ip_network(f"{ip_str}/{prefix}"))
        except ValueError as e:
            logger.warning(f"Invalid IP in whitelist: {ip_str} - {e}")

    return networks


def get_client_ip() -> str:
    """실제 클라이언트 IP 주소 반환"""
    return request.remote_addr


def is_ip_allowed(client_ip: str, whitelist: list) -> bool:
    """클라이언트 IP가 화이트리스트에 있는지 확인"""
    try:
        ip = ipaddress.ip_address(client_ip)
        for network in whitelist:
            if ip in network:
                return True
    except ValueError:
        return False
    return False


class IPWhitelistMiddleware:
    """IP 화이트리스트 보안 클래스"""

    def __init__(self, app=None):
        self.app = app
        self.whitelist = []
        self.enabled = True

        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        """Flask 앱 초기화"""
        self.app = app

        # 환경변수에서 설정 로드
        self.enabled = os.environ.get("IP_WHITELIST_ENABLED", "true").lower() == "true"
        whitelist_str = os.environ.get("IP_WHITELIST", "")
        trust_proxy = os.environ.get("TRUST_PROXY", "false").lower() == "true"
        proxy_depth = int(os.environ.get("PROXY_DEPTH", "1"))

        # 기본 localhost + 사용자 정의 IP
        full_whitelist = ",".join(DEFAULT_WHITELIST)
        if whitelist_str:
            full_whitelist += "," + whitelist_str

        self.whitelist = parse_ip_whitelist(full_whitelist)

        # 프록시 뒤에서 실행 시 ProxyFix 적용
        if trust_proxy:
            app.wsgi_app = ProxyFix(
                app.wsgi_app,
                x_for=proxy_depth,
                x_proto=1,
                x_host=1,
                x_prefix=1
            )
            app.logger.info(f"ProxyFix enabled (depth={proxy_depth})")

        # before_request 핸들러 등록
        app.before_request(self._check_ip)

        status = "enabled" if self.enabled else "disabled"
        app.logger.info(f"IP Whitelist: {status}, allowed networks: {len(self.whitelist)}")

    def _check_ip(self):
        """모든 요청에 대해 IP 검사 수행"""
        if not self.enabled:
            return None

        client_ip = get_client_ip()

        if not is_ip_allowed(client_ip, self.whitelist):
            current_app.logger.warning(
                f"Access denied - IP: {client_ip}, Path: {request.path}, Method: {request.method}"
            )
            abort(403, description="Access denied: IP not in whitelist")

        return None


def init_security(app):
    """
    보안 초기화 함수

    사용법:
        from security import init_security
        init_security(app)
    """
    return IPWhitelistMiddleware(app)
