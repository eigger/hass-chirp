# 개발과 테스트

[English](../development.md) | [한국어](development.md) | [README](../../README.ko.md)

최신 테스트 환경은 HA 2026.10.2·플러그인 0.13.373·Python 3.14.2 이상입니다. 지원 최소 버전은 HA 2025.3.0으로 유지하며, 별도 Python 3.13 환경에서 그 버전에 호환되는 플러그인 0.13.221로 검증합니다.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install -r requirements_test.txt -r requirements_lint.txt
.venv/bin/python -m pip check
.venv/bin/python -m ruff check .
.venv/bin/python -m ruff format --check .
.venv/bin/python -m pytest tests/components/chirp/ -v
```

최소 HA 검증은 별도 가상환경에서 `requirements_test_min.txt`를 설치해 같은 pytest 명령을 실행합니다. 테스트는 현재·최소 환경별 정확한 HA/플러그인 설치값을 확인하고 최소 환경이 `hacs.json`의 지원 하한과 일치하는지 검사합니다. 최신 테스트 환경을 갱신하는 것만으로 컴포넌트 지원 하한을 올리지 않습니다. 테스트 의존성은 런타임 manifest와 분리하며 호환 HA·플러그인 버전을 함께 검토합니다. 자세한 환경·검증 범위는 [적용 기준](../../STANDARDS.md)과 [체크리스트](../../ADOPTION_CHECKLIST.md)를 참고하세요.

## 도메인과 API 계약

통합 도메인은 `chirp`입니다(경로 `custom_components/chirp/`, 테스트 `tests/components/chirp/`). API 계약은 Chirp 저장소의 zod 스키마(`packages/shared/src/schema.ts`)이며, `tests/components/chirp/fixtures/status.json`은 그 샘플(`status.sample.json`)의 원본 복사본이고 다른 `status_*.json` fixture는 이를 변형한 것입니다(NVMe 위험, 새 SATA SSD, 대기 모드, 사라진 디스크). 브랜드 이미지는 `python scripts/generate_brand.py`로 재생성합니다(`custom_components/chirp/brand/README.md` 참고).
