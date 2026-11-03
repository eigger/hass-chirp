<!-- hass-standards:header:start -->
# Chirp Home Assistant Integration (hass-chirp)

Chirp 서버의 디스크 SMART 건강 상태·디스크와 CPU 온도, 호스트 메모리·부하·네트워크·전력·팬·전압 지표를 읽기 전용으로 연결하는 Home Assistant 커스텀 통합입니다.

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

디스크 SMART 건강 상태·온도와 호스트 지표를 보여 주는 셀프호스팅 모니터 [Chirp](https://github.com/eigger/chirp)를 Home Assistant에 **읽기 전용**으로 연결하는 커스텀 통합입니다. Chirp의 `/api/v1/status`를 기본 60초마다 읽어 호스트의 CPU 온도·메모리·부하·전력·팬·전압·네트워크 인터페이스와 각 디스크의 온도·건강 상태·SMART 카운터를 엔티티로 제공합니다.

## 주요 기능

- 모니터링 대상 호스트 기기(CPU 온도, 부팅 시각, "디스크 문제 있음", SMART 새로고침 버튼)와 디스크별 기기
- 디스크별 온도(대기 모드에서도 마지막 값 유지)·전원 켜짐 시간·건강 상태(`ok`/`warning`/`failing`과 사유, Chirp가 디스크를 읽기 전에는 Home Assistant의 *알 수 없음*)·SMART 문제 이진 센서
- 프로토콜별 카운터: SATA는 재할당·대기 중 섹터, SSD/NVMe는 마모율·가용 예비 공간·누적 기록량·미디어 오류
- 호스트 지표를 보고하는 Chirp 서버라면 메모리·스왑 사용률, CPU 사용률과 부하, CPU 패키지 전력, 팬 속도와 전압, 그리고 네트워크 인터페이스별 기기(수신·송신 속도, 누적량, 링크 상태와 속도). 각 값의 `scope` 속성으로 호스트 관점인지 Chirp 컨테이너 자체 관점인지 구분. 처음 발견했을 때 멈춰 있던 팬은 비활성으로 시작하니 엔티티 설정에서 켜세요([자세히](docs/ko/user-guide.md#지원-기능과-엔티티))
- 나중에 나타난 디스크·네트워크 인터페이스는 자동 추가, 사라진 것은 사용 불가로 표시
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

### API 키 확인 방법

1. chirp 대시보드(`http://<chirp 주소>/`)를 엽니다. 새로 설치했다면 먼저 관리자 계정을 만드세요. 대시보드를 먼저 연 사람이 관리자가 되므로 chirp 설치 직후 바로 만들어야 합니다.
2. 로그인한 뒤 **설정 → API 키**로 갑니다.
3. **복사**(또는 **보기**로 확인)를 누르고, Home Assistant의 chirp 통합에 chirp 호스트·포트와 함께 붙여 넣습니다.

같은 화면의 **재발급**은 새 키를 만듭니다. 이전 키는 즉시 동작하지 않으므로 통합에도 새 키를 넣어야 합니다(Home Assistant가 재인증을 요청합니다). 서버에서 `CHIRP_API_KEY`로 키를 지정했다면 읽기 전용으로 보이며 서버 설정에서 바꿔야 합니다. 서버에서 `node apps/server/dist/cli.js key show`로도 확인할 수 있습니다(Proxmox: `pct exec <CTID> -- node /opt/chirp/current/apps/server/dist/cli.js key show`, Docker: `docker exec chirp node apps/server/dist/cli.js key show`).

[자세한 안내](docs/ko/user-guide.md#설치)

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
| [사용자 가이드](docs/ko/user-guide.md) | 설정과 API 키, 엔티티·속성, 호스트·컨테이너 관점, 건강 상태 사유, 문제 해결 |
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
