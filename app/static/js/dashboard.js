/**
 * @fileoverview 대시보드 진입점 (ES6 Module)
 *
 * 이 파일은 대시보드 모듈의 진입점입니다.
 * 모든 기능은 dashboard/ 폴더의 모듈에서 구현됩니다.
 *
 * 모듈 구조:
 * - config.js  : 설정 상수
 * - state.js   : 상태 관리
 * - api.js     : API 호출
 * - ui.js      : UI 렌더링
 * - utils.js   : 유틸리티 함수
 * - index.js   : 메인 컨트롤러 (초기화, 이벤트)
 *
 * @version 2.0.0
 * @author Refactored with Clean Architecture
 */

// 메인 모듈 import (자동 초기화됨)
import './dashboard/index.js';

// 디버깅용 콘솔 출력
console.log('📊 Dashboard module loaded (v2.0)');
