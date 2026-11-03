# 공통 규칙 적용 체크리스트

hass-chirp 신규 통합 작성 시점(2026-11-03)의 실제 확인 기록입니다. [사용법과 판정 기준](https://github.com/eigger/hass-repo-standards/blob/main/docs/checklist.md)을 따르며 규칙은 `STANDARDS.md`의 표준 v1.1.5(`f56987f7f765a774c926fb8005fe5df68bb32451`)에서 확인합니다. 이 저장소는 아직 커밋·원격 게시 전이므로 원격 CI, HACS·Hassfest Action, 첫 Release는 TODO입니다.

## 검토 대상

| 항목 | 값 |
|---|---|
| 통합 리포 / 기본 브랜치 | eigger/hass-chirp / master (원격 게시 후 실제 값 확인 필요) |
| domain / 구현 경로 | chirp / custom_components/chirp/ |
| 서버 | eigger/chirp (API v1, `packages/shared/src/schema.ts`) |
| 검토한 표준 | v1.1.5 / f56987f7f765a774c926fb8005fe5df68bb32451 |
| profile / 테스트 경로 | integration / ha, tests/components/chirp/ |
| 검토일 | 2026-11-03 |

상태: `TODO` = 미확인·미충족, `PASS` = 근거로 확인, `EXCEPTION` = 기록된 예외, `N/A` = 해당 없음.

## 채택·구조·사용자 데이터

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| GOV-01, GOV-02 | `STANDARDS.md`에 표준 SHA·profile·기본 브랜치·예외 기록, workflow는 검토 릴리스로 고정 | PASS | STANDARDS.md; 세 공통 workflow 호출 `@v1.1.5`; `check_integration.py --check` 성공 |
| GOV-03 | 채택 PR | TODO | 저장소 게시 후 PR로 채택 검토 |
| GOV-04, GOV-05 | 중앙 현황표 갱신, 구현과 독립 리뷰 분리 | TODO | 호출 측(조율 담당)이 등록·독립 검토 수행 |
| HA-01, HA-13 | `custom_components/chirp/`와 domain 일치, Core 대응 구조 | PASS | api/config_flow/coordinator/entity/diagnostics/플랫폼·`runtime_data` 구성 |
| HA-02 | manifest 필수 필드·키 순서·동작 선언, 자가 품질 등급 없음 | PASS | domain, name, 이후 알파벳순; categories `computers_network.monitoring`; integration_type device; local_polling; requirements=[] |
| HA-03 (권장) | 모듈 역할 분리 | PASS | api(프로토콜)와 엔티티 분리, const/entity 공통 |
| HA-04, HA-08 | UI 설정·중복·안정적 식별, options/reauth/reconfigure | PASS | test_config_flow: 생성·오류·중복(주소 갱신)·reauth(wrong_instance)·reconfigure·options; unique_id=instance.id |
| HA-05, HA-06 | setup 실패 구분, unload/reload 정리, async·timeout | PASS | test_init: retry/auth 구분, listener·refresh timer 정리; aiohttp 15초 timeout, 공유 세션 |
| HA-07 | 중복 polling 방지, 실패 시 마지막 값 유지, unavailable 정확성 | PASS | 단일 coordinator; test_coordinator 연속 실패·복구·reauth 1회; 사라진 디스크 unavailable |
| HA-08 | unique ID·device class·단위·state class | PASS | test_sensor/test_binary_sensor; 디스크 unique_id `{instance}_{disk}_{key}` |
| HA-09, HA-10 | Bluetooth·imagespec·blesession | N/A | HTTP 통합, 해당 라이브러리 미사용 |
| HA-11 | strings.json·translations(en/ko) 일치 | PASS | strings.json=en.json, ko 키 동일; config/options/entity/exceptions |
| HA-12 | 로그·diagnostics 비식별화와 redaction 테스트 | PASS | test_diagnostics; API 오류 메시지에 URL·키 미포함(test_api) |

## 테스트·CI·릴리스·문서

| 규칙 ID | 확인 항목 | 상태 | 근거 / 남은 작업 |
|---|---|---|---|
| TEST-03, TEST-08 | 실제 HA 테스트, 현재·최소 환경 분리, 경로 일치 | PASS | 현재 HA 2026.10.2/Python 3.14와 최소 HA 2025.3.0/Python 3.13 각각 96 passed, `pip check` 성공 |
| 정적 검사 | Ruff·format | PASS | `ruff check .`, `ruff format --check .` 성공 |
| CI-01~13 | 공통 workflow, Dependabot, 표준 갱신 | PASS (정적) | `.github/workflows/*`, `dependabot.yml`; 원격 실행은 TODO |
| HACS-01~04 | README/LICENSE/hacs.json, ZIP release | PASS (정적) | `hacs.json` filename `chirp.zip`; 원격 HACS Action·실제 Release asset은 TODO |
| Hassfest | manifest·strings 검증 | TODO | 로컬 실행 불가(Hassfest는 HA Core checkout 필요); manifest·strings 규칙은 수동 점검 |
| DOC-01~06 | README 관리 영역·배지·설치 링크·양언어 | PASS | `check_integration.py --write-readmes` 후 `--check` 성공 |
| REL-01~03 | 버전·migration | N/A | 최초 버전 0.1.0, entry VERSION 1; migration 대상 없음 |

## 수동 검증 한계

| 항목 | 상태 | 비고 |
|---|---|---|
| 실제 Chirp 서버·실물 디스크 | 미검증 | HTTP 경계를 모의한 실제 HA 테스트만 수행 |
| HA frontend 표시, 로컬 brand UI | 미검증 | PNG 파일 생성·시각 확인만 수행; 로컬 brand 표시는 HA 2026.3+ |
| 원격 Tests/Validate, 첫 Release ZIP | 미검증 | 저장소 게시 후 확인 |
