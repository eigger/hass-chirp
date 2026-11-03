<!-- hass-standards:header:start -->
# Chirp Home Assistant Integration (hass-chirp)

Chirp 서버의 디스크 SMART 건강 상태·디스크 온도·CPU 온도를 읽기 전용으로 연결하는 Home Assistant 커스텀 통합입니다.

[English](README.md) | **한국어**

<!-- hass-standards:badges:start -->
[![Release](https://img.shields.io/github/v/release/eigger/hass-chirp?style=flat)](https://github.com/eigger/hass-chirp/releases)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5?style=flat)](#설치)
[![Home Assistant minimum](https://img.shields.io/badge/HA-%E2%89%A5%202025.3.0-41BDF5?style=flat)](hacs.json)
[![Tests](https://img.shields.io/github/actions/workflow/status/eigger/hass-chirp/tests.yml?branch=master&style=flat&label=Tests)](https://github.com/eigger/hass-chirp/actions/workflows/tests.yml)
[![Validate](https://img.shields.io/github/actions/workflow/status/eigger/hass-chirp/validate.yml?branch=master&style=flat&label=Validate)](https://github.com/eigger/hass-chirp/actions/workflows/validate.yml)
[![License](https://img.shields.io/github/license/eigger/hass-chirp?style=flat)](LICENSE)
[![Downloads](https://img.shields.io/github/downloads/eigger/hass-chirp/latest/total?style=flat&color=41BDF5&label=Downloads)](https://github.com/eigger/hass-chirp/releases)
<!-- hass-standards:badges:end -->
<!-- hass-standards:header:end -->

![Chirp](custom_components/chirp/brand/logo.png)

디스크 SMART 건강 상태와 온도를 보여 주는 셀프호스팅 모니터 [Chirp](https://github.com/eigger/chirp)를 Home Assistant에 **읽기 전용**으로 연결하는 커스텀 통합입니다. Chirp의 `/api/v1/status`를 기본 60초마다 읽어 호스트 CPU 온도와 각 디스크의 온도·건강 상태·SMART 카운터를 엔티티로 제공합니다.

## 주요 기능

- 모니터링 대상 호스트 기기(CPU 온도, 부팅 시각, "디스크 문제 있음", SMART 새로고침 버튼)와 디스크별 기기
- 디스크별 온도(대기 모드에서도 마지막 값 유지)·전원 켜짐 시간·건강 상태(`ok`/`warning`/`failing`과 사유, Chirp가 디스크를 읽기 전에는 Home Assistant의 *알 수 없음*)·SMART 문제 이진 센서
- 프로토콜별 카운터: SATA는 재할당·대기 중 섹터, SSD/NVMe는 마모율·가용 예비 공간·누적 기록량·미디어 오류
- 나중에 나타난 디스크는 자동 추가, 사라진 디스크는 사용 불가로 표시
- 짧은 장애 동안은 마지막 값을 유지하고, 연속 3회 조회에 실패하면 Chirp가 다시 응답할 때까지 엔티티를 사용할 수 없음으로 표시. 연속 오류 횟수 센서는 진단용으로 계속 표시

## 요구사항

Home Assistant **2025.3.0 이상**, 접근 가능한 [Chirp](https://github.com/eigger/chirp) 서버와 API 키가 필요합니다. 로컬 HTTP/HTTPS 폴링만 사용하며 Bluetooth는 필요 없습니다.

## 설치

<!-- hass-standards:installation:start -->
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=eigger&repository=hass-chirp&category=integration)
<!-- hass-standards:installation:end -->

1. 모니터링할 장비에 Chirp를 설치합니다. Proxmox VE에서는 원클릭 스크립트가 컨테이너를 만들어 줍니다.

   ```sh
   bash -c "$(curl -fsSL https://raw.githubusercontent.com/eigger/chirp/master/proxmox/ct/chirp.sh)"
   ```

2. HACS에서 `eigger/hass-chirp`를 사용자 지정 **Integration** 저장소로 추가하고 **Chirp** 를 설치한 뒤 Home Assistant를 재시작합니다.
3. **설정 → 기기 및 서비스 → 통합 추가 → Chirp** 로 이동합니다.
4. Chirp의 **주소**(IP 또는 이름), **포트**(기본 `80`), **API 키**를 입력합니다. Chirp를 HTTPS로 제공할 때만 *HTTPS 사용*을 켜고, 신뢰하는 서버의 자체 서명 인증서일 때만 *SSL 인증서 확인*을 끕니다.

API 키는 `chp_`로 시작합니다. Chirp 호스트에서 `cat /var/lib/chirp/api-key`로 확인합니다(Proxmox 컨테이너 안이라면 `pct exec <ctid> -- cat /var/lib/chirp/api-key`). [자세한 안내](docs/ko/user-guide.md#설치)

## 사용 방법

```yaml
action: button.press
target:
  entity_id: button.pve_refresh_smart_data
```

실제 설치에서 생성된 엔티티 ID를 사용하세요. 이 버튼은 Chirp에 SMART 데이터를 지금 다시 읽도록 요청한 뒤 새 값이 들어올 때까지 몇 번 더 조회하며(5초 간격, 최대 30초), Chirp의 쿨다운(429)은 오류로 취급하지 않습니다. 통합 옵션에서 조회 주기(30~3600초)를 바꿀 수 있습니다. [문제 해결](docs/ko/user-guide.md#제한-사항과-문제-해결)

## 문서

| 문서 | 내용 |
|---|---|
| [사용자 가이드](docs/ko/user-guide.md) | 설정과 API 키, 엔티티·속성, 건강 상태 사유, 문제 해결 |
| [개발과 테스트](docs/ko/development.md) | 실제 HA 테스트, 최소/최신 환경, 의존성과 명령 |
| [적용 기준](STANDARDS.md) · [체크리스트](ADOPTION_CHECKLIST.md) | 공통 규칙과 검증 기록 |

<!-- hass-standards:support:start -->
## 지원

- [Issues](https://github.com/eigger/hass-chirp/issues): 버그를 신고하거나 기능을 요청하세요.
- [Discussions](https://github.com/eigger/hass-chirp/discussions): 질문하고 사용 경험을 공유하세요.
<!-- hass-standards:support:end -->

<!-- hass-standards:related-projects:start -->
## 관련 프로젝트

- [Chirp](https://github.com/eigger/chirp): 이 통합이 연결하는 셀프호스팅 디스크·CPU 모니터 서버입니다.
<!-- hass-standards:related-projects:end -->

<!-- hass-standards:license:start -->
## 라이선스

[MIT License](LICENSE) 라이선스로 배포됩니다.
<!-- hass-standards:license:end -->
