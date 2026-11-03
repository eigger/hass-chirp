# 사용 안내와 문제 해결

[English](../user-guide.md) | [한국어](user-guide.md) | [README](../../README.ko.md)

## 요구사항

- Home Assistant **2025.3.0 이상**, 접근 가능한 [Chirp](https://github.com/eigger/chirp) 서버와 API 키.
- 로컬 HTTP/HTTPS 폴링만 사용하며 Bluetooth 어댑터나 프록시는 쓰지 않습니다.
- 통합 도메인은 `chirp`(표시 이름 **Chirp**)입니다.

## 설치

### 1. Chirp 서버 설치

Chirp는 디스크와 CPU를 감시할 장비에서 실행합니다. Proxmox VE에서는 노드에서 원클릭 스크립트를 실행하면 컨테이너를 만들고 Chirp를 설치합니다.

```sh
bash -c "$(curl -fsSL https://raw.githubusercontent.com/eigger/chirp/master/proxmox/ct/chirp.sh)"
```

Chirp는 기본적으로 **80** 포트(`CHIRP_PORT`)에서 동작하며 대시보드는 `http://<주소>/`입니다.

### 2. API 키 확인

키는 `chp_`로 시작하며 Chirp 호스트에 저장되어 있습니다.

```sh
cat /var/lib/chirp/api-key
# 또는
node /opt/chirp/current/apps/server/dist/cli.js key show
```

Proxmox 컨테이너라면 명령 앞에 `pct exec <ctid> --`를 붙입니다(예: `pct exec 105 -- cat /var/lib/chirp/api-key`). `... cli.js key rotate`는 새 키를 만들며, 이후 Home Assistant의 재인증 화면에서 키를 갱신하세요. 서버에 `CHIRP_API_KEY`가 설정돼 있으면 키 파일보다 우선합니다.

### 3. 통합 설치와 추가

1. Home Assistant 2025.3.0 이상의 HACS에서 `eigger/hass-chirp`를 사용자 지정 **Integration** 저장소로 추가합니다.
2. **Chirp** 를 설치하고 Home Assistant를 재시작합니다.
3. **설정 → 기기 및 서비스 → 통합 추가 → Chirp** 로 이동합니다.
4. **주소**(IP 또는 호스트 이름, `http://`나 경로 없이), **포트**(기본 `80`), **API 키**를 입력합니다. 리버스 프록시 등으로 Chirp를 HTTPS로 제공할 때만 **HTTPS 사용**을 켭니다.

Chirp 인스턴스마다 고유 ID가 있습니다. 같은 인스턴스를 다시 추가하면(예: IP가 바뀐 경우) 중복 항목을 만들지 않고 저장된 주소와 포트를 갱신합니다. 나중에 주소를 바꾸려면 통합 항목의 **재구성**을 사용하세요. 같은 인스턴스만 허용합니다. 저장된 주소에서 다른 Chirp 인스턴스가 응답하면(예: DHCP 주소 변경, 서버 재설치) 갱신은 실패로 처리되어 조회 오류 센서에 `ChirpInstanceMismatchError`가 기록되고 그 인스턴스의 엔티티는 만들지 않습니다. **재구성**으로 올바른 서버를 지정하세요. 조회 주기(기본 60초, 30~3600초)는 통합 옵션입니다.

수동 설치는 `custom_components/chirp`를 HA 설정 디렉터리의 같은 경로에 복사하고 재시작합니다. 제거는 통합 항목 삭제 후 HACS에서 제거하거나 해당 디렉터리를 지우고 재시작합니다.

## 지원 기능과 엔티티

서버가 실제로 보고하는 항목에 해당하는 엔티티만 생성합니다. 기본 비활성 엔티티는 엔티티 설정에서 켤 수 있습니다.

**호스트 기기**(Chirp 호스트 이름, 모델은 CPU 모델):

| 엔티티 | 비고 |
|---|---|
| CPU 온도 | 패키지 온도, °C |
| CPU 최고 온도 | 기본 비활성 |
| `<코어>` 온도 | CPU 코어별, 기본 비활성 |
| 부팅 시각 | 진단용; 수집 시각 − 가동 시간 |
| 연속 조회 오류 | 진단용; 속성 `last_error`, `last_error_at`, `last_success_at` |
| 디스크 문제 있음 | 문제 센서; 디스크 하나라도 `warning`/`failing`이면 켜짐 |
| SMART 데이터 새로고침 | 버튼; Chirp에 SMART를 지금 다시 읽도록 요청 |

**디스크 기기**(디스크마다 하나, 이름은 `모델 (시리얼 뒤 4자리)`, 호스트에 연결):

| 엔티티 | 비고 |
|---|---|
| 온도 | 대기 모드에서도 마지막 값 유지; 속성 `standby` |
| 전원 켜짐 시간 | 누적 증가 |
| 전원 켜짐 횟수 | 진단용 |
| 건강 상태 | `ok`, `warning`, `failing`, `unknown`; 속성 `reasons` |
| SMART 문제 | 문제 센서; `warning`/`failing`이면 켜짐; 속성 `reasons`, `smart_passed` |
| 재할당된 섹터, 대기 중 섹터 | SATA, 기본 활성 |
| 오프라인 복구 불가 섹터, UDMA CRC 오류 | SATA, 진단용 |
| 마모율 | SSD·NVMe, 사용한 수명 비율 |
| 가용 예비 공간 | NVMe, % |
| 누적 기록량 | NVMe, TB |
| 미디어 오류, 비정상 종료 | NVMe, 진단용 |

새 디스크는 다음 조회에서 자동으로 추가됩니다. 서버 시작 후 아직 읽지 못한 디스크(standby·읽기 실패)는 임시 ID `dev_<이름>`만 가지므로, Chirp가 첫 읽기 후 영구 ID를 보고할 때 엔티티를 만듭니다. Chirp 응답에서 사라진 디스크는 사용 불가로 표시되며, 영구히 제거했다면 기기 페이지에서 해당 기기를 삭제하세요. 호스트 기기는 삭제할 수 없습니다.

### 건강 상태 사유

`reasons` 속성은 `code`와 선택적 `value`를 가진 객체 목록입니다. 코드는 Chirp API의 값입니다: `smart_failed`, `nvme_critical_warning`, `spare_below_threshold`, `reallocated_sectors`, `pending_sectors`, `offline_uncorrectable`, `media_errors`, `wear_high`, `temperature_high`, `not_read`. 건강 상태 `unknown`(알 수 없음)은 Chirp가 디스크를 읽지 못했다는 뜻(예: `not_read`)이며 문제로 보고하지 않습니다.

## 사용 예시

```yaml
action: button.press
target:
  entity_id: button.pve_refresh_smart_data
```

실제 설치에서 생성된 엔티티를 선택하세요. Chirp는 새로고침 요청 횟수를 제한(HTTP 429)하며, 통합은 이를 성공으로 처리하고 데이터는 계속 갱신합니다.

디스크 위험을 알리는 자동화 예시:

```yaml
triggers:
  - trigger: state
    entity_id: binary_sensor.pve_any_disk_problem
    to: "on"
actions:
  - action: notify.notify
    data:
      message: 디스크에서 SMART 문제가 보고되었습니다.
```

## 제한 사항과 문제 해결

- SMART 새로고침 요청을 제외하면 읽기 전용입니다. 임계값과 설정은 Chirp에서 바꾸세요.
- Home Assistant는 `GET /api/v1/status`만 조회합니다. SMART 값은 Chirp 자체 일정으로 바뀌므로 조회 주기를 줄여도 SMART 데이터가 더 최신이 되지는 않습니다.
- Chirp에 연결할 수 없으면 엔티티가 마지막 값을 유지하고 연속 조회 오류 횟수가 늘며, 다음 성공 시 0으로 돌아갑니다. 인증 실패는 Home Assistant의 재인증을 시작합니다.
- **연결 불가**: 주소·포트·HTTPS 스위치를 확인하고 브라우저에서 `http://<주소>:<포트>/health`를 열어 보세요. 주소 칸에는 URL이 아니라 호스트 이름·IPv4·IPv6 주소만 입력합니다. IPv6 zone ID(`%eth0`)는 지원하지 않습니다.
- **인증 오류**: `/var/lib/chirp/api-key`에서 키를 다시 복사하세요. 재인증 중 다른 Chirp 인스턴스의 키는 거부됩니다.
- API 버전: 이 버전은 Chirp API 버전 1을 지원합니다. 더 새로운 버전이 보고되면 경고를 한 번 기록하고 알려진 필드는 계속 사용합니다.
- 이슈 보고서에서 API 키·호스트 이름·IP·디스크 시리얼 번호를 제거하세요. 진단 정보는 자동으로 가려집니다.
- 테스트는 실제 Home Assistant와 모의 HTTP 응답을 사용하며 실제 Chirp 서버를 보증하지 않습니다.
