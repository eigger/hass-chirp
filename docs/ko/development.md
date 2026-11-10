# 개발과 테스트

[English](../development.md) | [한국어](development.md) | [README](../../README.ko.md)

최신 테스트 환경은 HA 2026.10.4·플러그인 0.13.375이며, 최소 지원 환경은 HA 2026.10.0·플러그인 0.13.371입니다. 두 환경 모두 Python 3.14.2 이상을 사용합니다. 기존 HA 2025.3.0 테스트 환경에 고정된 Home Assistant와 aiohttp의 알려진 취약점을 제거하기 위해 지원 하한을 올렸습니다.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt -r requirements_lint.txt
.venv/bin/python -m pip check
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest tests/components/chirp/ -v
```

최소 HA 검증은 별도 가상환경에서 `requirements_test_min.txt`를 설치해 같은 pytest 명령을 실행합니다. 테스트는 현재·최소 환경별 정확한 HA/플러그인 설치값을 확인하고 최소 환경이 `hacs.json`의 지원 하한과 일치하는지 검사합니다. Dependabot은 최신 테스트 환경을 자동 갱신하고 pip 보안 업데이트를 별도 그룹으로 묶습니다. `requirements_test_min.txt`의 정확한 HA·플러그인 조합은 지원 하한이므로 자동 갱신에서 제외합니다. 최소 환경은 `hacs.json`, CI 기대 버전과 지원 문서를 함께 바꾸는 명시적인 지원 하한 변경 PR에서만 갱신하며 환경 테스트가 불일치를 감지합니다. 최소 환경에 보안 경고가 생기면 지원 하한 상향 필요성을 검토합니다. 최신 테스트 환경만 갱신하면 지원 하한은 바뀌지 않습니다. 테스트 의존성은 런타임 manifest와 분리하며 호환 HA·플러그인 버전을 함께 검토합니다. 자세한 환경·검증 범위는 [적용 기준](../../STANDARDS.md)과 [체크리스트](../../ADOPTION_CHECKLIST.md)를 참고하세요.

## 도메인과 API 계약

통합 도메인은 `chirp`입니다(경로 `custom_components/chirp/`, 테스트 `tests/components/chirp/`). API 계약은 Chirp 저장소의 zod 스키마(`packages/shared/src/schema.ts`)이며, `tests/components/chirp/fixtures/status.json`은 그 샘플(`status.sample.json`)의 원본 복사본이고, `status_container_scope.json`·`status_null_sections.json`·`status_legacy.json`은 `status.container-scope.json`·`status.null-sections.json`·`status.legacy.json`의 원본 복사본입니다(컨테이너 관점 호스트 지표, 모든 지표 섹션 `null`, 호스트 지표가 없는 이전 서버). 다른 `status_*.json` fixture는 샘플을 변형한 것입니다(NVMe 위험, 새 SATA SSD, 대기 모드, 사라진 디스크). 호스트 지표의 `scope`가 `host`·`container`가 아닌 값(앞으로 서버가 추가할 수 있는 값)이면 각 엔티티의 `scope` 속성에는 그대로 보여 주고, **지표 관점** 요약 센서는 추측하지 않고 *알 수 없음*이 됩니다(`sensor.py`의 `_data_scope` 참고). 팬·전압·전력 측정원 이름은 칩 레이블에 그 뜻의 영어 단어가 이미 있으면 "speed"/"voltage"/"power" 접미사를 빼고 레이블만 씁니다(`sensor.py`의 `label_words`). 칩 레이블은 영어이므로 한국어 이름도 레이블만 보입니다(`power1 전력`이 아니라 `power1`). 브랜드 이미지는 `python scripts/generate_brand.py`로 재생성합니다(`custom_components/chirp/brand/README.md` 참고).
