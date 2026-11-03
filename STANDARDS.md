# 적용한 공통 규칙
- 표준: https://github.com/eigger/hass-repo-standards/tree/v1.1.5
- 참조 커밋 SHA: f56987f7f765a774c926fb8005fe5df68bb32451
- Standards release: v1.1.5
- Resolved standards SHA: f56987f7f765a774c926fb8005fe5df68bb32451
- 채택일: 2026-11-03
- profile: integration / ha
- 기본 브랜치: master; domain: chirp
- 적용 점검표: [ADOPTION_CHECKLIST.md](ADOPTION_CHECKLIST.md)
- 중앙 현황표: https://github.com/eigger/hass-repo-standards/blob/main/docs/adoption-status.md
- 테스트 경로: `tests/components/chirp/`
- 현재 테스트 환경: Python 3.14.2 이상 / HA 2026.10.2 / pytest-homeassistant-custom-component 0.13.373 (`requirements_test.txt`)
- 컴포넌트 지원 최소 환경: Python 3.13 / HA 2025.3.0 / pytest-homeassistant-custom-component 0.13.221 (`requirements_test_min.txt`)
- 최신 테스트 버전 갱신과 컴포넌트 지원 하한 변경을 구분하며 지원 하한은 2025.3.0입니다.
- 최소 외부 라이브러리: 해당 없음 (`manifest.requirements=[]`)

## 신규 통합 작성 기록 (2026-11-03)

hass-chirp는 Chirp 서버(eigger/chirp)의 디스크 SMART·CPU 온도 모니터링 API를 읽는 신규 통합입니다. 구조·CI·문서는 같은 표준 v1.1.5를 채택한 hass-kibble을 기준으로 작성했으며, 중앙 `manage_integration.py plan --mode create`는 사용하지 않았습니다. 이 도구는 표준 저장소 checkout이 검토한 정확한 SHA와 일치하고 release 원격 검증이 필요하므로, 같은 릴리스 v1.1.5를 이미 채택한 kibble의 관리 파일(workflow caller·README 관리 영역·STANDARDS/체크리스트 형식)을 복제해 `domain: chirp`, `ha-components: 'binary_sensor button sensor'`로 수정했습니다. README 관리 영역은 중앙 `check_integration.py --write-readmes`로 생성했습니다.

- 통합 도메인은 `chirp`, 표시 이름은 "Chirp"입니다.
- HA-02: Chirp는 호스트의 디스크 SMART 건강 상태와 CPU·디스크 온도를 보고하는 셀프호스팅 모니터이므로 주 분류 `computers_network.monitoring`을 선택했습니다. 엔티티 플랫폼에서 추정하지 않았고 보조 분류는 없습니다. 근거는 `.hass-standards.json.categories_review`에 기록했습니다. `integration_type`은 `device`입니다.
- HACS-02~04: Custom 상태를 유지하며 `zip_release: true`, `filename: chirp.zip`과 중앙 Release caller를 사용합니다. 첫 Release는 manifest 버전 0.1.0과 일치하는 tag로 게시해야 ZIP이 첨부됩니다.
- 브랜드: 원본 아트워크를 `scripts/generate_brand.py`로 생성합니다. 출처·라이선스·재생성·해시는 `custom_components/chirp/brand/README.md`에 있습니다.
- 문서: 영문 `README.md`, 한국어 `README.ko.md`, 이전 경로 `README.en.md` 안내, `docs/`와 `docs/ko/` 사용자·개발 문서를 제공합니다.

## 검증 환경과 경계

실제 HA loader·config entry manager·플랫폼·flow·service·registry를 실행하고 HTTP 응답만 플러그인의 `aioclient_mock`으로 대체합니다. HA 가짜 모듈과 FakeHass는 사용하지 않습니다. API 계약은 Chirp 저장소의 zod 스키마(`packages/shared/src/schema.ts`)와 샘플이며 `tests/components/chirp/fixtures/status.json`은 그 샘플의 원본 복사본입니다. 다른 `status_*.json`은 변형입니다.

`test_supported_environment.py`는 최소 테스트 HA가 `hacs.json`의 지원 하한과 일치하고 현재 테스트 HA가 그 하한 이상인지 확인합니다. 최신 환경만 갱신해도 컴포넌트 지원 최소를 올리지 않습니다.

최소 환경은 당시 HA 자체가 고정한 yanked `aiohttp==3.11.13`을 정확히 재현하며 최소 검증 파일에만 명시합니다. 최소 플러그인의 Bluetooth helper import용 간접 패키지는 [당시 공식 Bluetooth manifest](https://github.com/home-assistant/core/blob/2025.3.0/homeassistant/components/bluetooth/manifest.json)의 여섯 버전을 `constraints/homeassistant-min.txt`에 고정합니다. 이 통합의 런타임 Bluetooth 의존성은 아닙니다. Dependabot의 `exclude-paths`로 이 역사적 최소 requirements와 constraints를 자동 갱신에서 제외합니다.

실제 Chirp 서버·기기 SMART 데이터와의 실물 검증은 수행하지 않았습니다. HACS·Hassfest 및 GitHub Actions 결과는 저장소 게시 후 체크리스트에서 별도로 확인합니다.

## 예외

현재 기록된 적용 예외는 없습니다.
