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

1. chirp 대시보드(`http://<chirp 주소>/`)를 엽니다. 새로 설치했다면 먼저 관리자 계정을 만드세요. 대시보드를 먼저 연 사람이 관리자가 되므로 chirp 설치 직후 바로 만들어야 합니다.
2. 로그인한 뒤 **설정 → API 키**로 갑니다.
3. **복사**(또는 **보기**로 확인)를 누르고, Home Assistant의 chirp 통합에 chirp 호스트·포트와 함께 붙여 넣습니다.

같은 화면의 **재발급**은 새 키를 만듭니다. 이전 키는 즉시 동작하지 않으므로 통합에도 새 키를 넣어야 합니다(Home Assistant가 재인증을 요청합니다). 서버에서 `CHIRP_API_KEY`로 키를 지정했다면 읽기 전용으로 보이며 서버 설정에서 바꿔야 합니다. 서버에서 `node apps/server/dist/cli.js key show`로도 확인할 수 있습니다(Proxmox: `pct exec <CTID> -- node /opt/chirp/current/apps/server/dist/cli.js key show`, Docker: `docker exec chirp node apps/server/dist/cli.js key show`).

### 3. 통합 설치와 추가

1. Home Assistant 2025.3.0 이상의 HACS에서 `eigger/hass-chirp`를 사용자 지정 **Integration** 저장소로 추가합니다.
2. **Chirp** 를 설치하고 Home Assistant를 재시작합니다.
3. **설정 → 기기 및 서비스 → 통합 추가 → Chirp** 로 이동합니다.
4. **주소**(IP 또는 호스트 이름, `http://`나 경로 없이), **포트**(기본 `80`), **API 키**를 입력합니다. 리버스 프록시 등으로 Chirp를 HTTPS로 제공할 때만 **HTTPS 사용**을 켭니다. **SSL 인증서 확인**은 기본으로 켜져 있으며, 그 프록시가 자체 서명 인증서를 쓰고 서버를 신뢰할 때만 끄세요.

Chirp 인스턴스마다 고유 ID가 있습니다. 같은 인스턴스를 다시 추가하면(예: IP가 바뀐 경우) 중복 항목을 만들지 않고 저장된 주소·포트·HTTPS 설정과 API 키를 갱신합니다. 새 키는 같은 인스턴스에서 인증에 성공했을 때만 저장되므로, 교체한 키를 빠르게 반영하는 방법으로도 쓸 수 있습니다. 나중에 주소나 HTTPS 설정을 바꾸려면 통합 항목의 **재구성**을 사용하세요. 같은 인스턴스만 허용합니다. 저장된 주소에서 다른 Chirp 인스턴스가 응답하면(예: DHCP 주소 변경, 서버 재설치) 갱신은 실패로 처리되어 조회 오류 센서에 `ChirpInstanceMismatchError`가 기록되고 그 인스턴스의 엔티티는 만들지 않습니다. **재구성**으로 올바른 서버를 지정하세요. 조회 주기(기본 60초, 30~3600초)는 통합 옵션입니다.

수동 설치는 `custom_components/chirp`를 HA 설정 디렉터리의 같은 경로에 복사하고 재시작합니다. 제거는 통합 항목 삭제 후 HACS에서 제거하거나 해당 디렉터리를 지우고 재시작합니다.

## 지원 기능과 엔티티

서버가 실제로 보고하는 항목에 해당하는 엔티티만 생성합니다. 기본 비활성 엔티티는 엔티티 설정에서 켤 수 있습니다.

**호스트 기기**(Chirp 호스트 이름, 모델은 CPU 모델):

| 엔티티 | 비고 |
|---|---|
| CPU 온도 | 패키지 온도, °C |
| CPU 최고 온도 | 기본 비활성 |
| `<코어>` 온도 | CPU 코어별, 기본 비활성. 코어 레이블로 식별하므로(`Core 0` → `..._cpu_core_temperature_core_0`) 서버가 코어 순서를 바꿔도 값이 같은 엔티티에 남습니다. 같은 레이블이 반복되면 `_2`, `_3`…을 붙이고, 레이블이 없는 코어는 위치(`index_<n>`)를 씁니다 |
| 부팅 시각 | 진단용; 수집 시각 − 가동 시간 |
| 연속 조회 오류 | 진단용; Chirp가 꺼져 있어도 사용 가능 상태 유지; 속성 `last_error`, `last_error_at`, `last_success_at` |
| 디스크 문제 있음 | 문제 센서; 디스크 하나라도 `warning`/`failing`이면 켜짐 |
| SMART 데이터 새로고침 | 버튼; Chirp에 SMART를 지금 다시 읽도록 요청한 뒤 몇 번 더 조회해 결과를 반영 |

**디스크 기기**(디스크마다 하나, 이름은 `모델 (시리얼 뒤 4자리)`, 호스트에 연결):

| 엔티티 | 비고 |
|---|---|
| 온도 | 대기 모드에서도 마지막 값 유지; 속성 `standby` |
| 전원 켜짐 시간 | 누적 증가 |
| 전원 켜짐 횟수 | 진단용 |
| 건강 상태 | `ok`, `warning`, `failing`; Chirp가 판정을 내리지 못하면 Home Assistant의 *알 수 없음*; 속성 `reasons` |
| 건강 상태 사유 | 원인을 상태값으로 표시(예: `온도 높음 (70 °C)`); 전체 원본은 속성 `reasons` |
| SMART 문제 | 문제 센서; `warning`/`failing`이면 켜짐; 속성 `reasons`, `smart_passed` |
| 재할당된 섹터, 대기 중 섹터 | SATA, 기본 활성 |
| 오프라인 복구 불가 섹터, UDMA CRC 오류 | SATA, 진단용 |
| 마모율 | SSD·NVMe, 사용한 수명 비율 |
| 가용 예비 공간 | NVMe, % |
| 누적 기록량 | NVMe, TB |
| 미디어 오류, 비정상 종료 | NVMe, 진단용 |

**호스트 지표**(호스트 기기에 붙음. 이 지표를 보고하는 Chirp 서버에서만, 아래 참고):

| 엔티티 | 키(unique ID 접미사) | 단위·분류 | 기본값 |
|---|---|---|---|
| 메모리 사용률 | `memory_used_percent` | %, measurement | 활성 |
| 메모리 사용량 | `memory_used` | 데이터 크기(GiB로 표시), measurement | 비활성 |
| 전체 메모리 | `memory_total` | 데이터 크기(GiB) | 진단용, 비활성 |
| 스왑 사용률 | `swap_used_percent` | %, measurement; 호스트에 스왑이 있을 때만 | 활성 |
| CPU 사용률 | `cpu_usage_percent` | %, measurement; Chirp가 샘플 두 개를 모으기 전에는 *알 수 없음* | 활성 |
| 부하 (1분) | `load_1m` | measurement | 활성 |
| 부하 (5분), 부하 (15분) | `load_5m`, `load_15m` | measurement | 비활성 |
| CPU 패키지 전력 | `package_power` | 전력, W, measurement; Chirp에 RAPL 또는 hwmon CPU 전력 측정원이 있을 때(첫 샘플에서는 *알 수 없음*) | 활성 |
| `<레이블>` 전력 | `power_source_<id>` | 전력, W, measurement; RAPL 영역·hwmon 전력 값마다 하나 | 비활성 |
| `<레이블>` 속도 | `fan_<id>` | rpm, measurement | 처음 발견했을 때 돌고 있던 팬만 활성, 나머지는 비활성(아래 참고) |
| `<레이블>` 전압 | `voltage_<id>` | 전압, V, measurement | 비활성 |
| 지표 관점 | `data_scope` | `host`, `container`, `mixed`; 속성 `memory_scope`, `load_scope`, `network_scope` | 진단용, 활성 |

부하 센서와 CPU 사용률에는 `cpu_count` 속성(그 관점의 논리 CPU 수)이 있습니다. 팬·전압·전력 측정원 이름은 모니터링 칩의 레이블 뒤에 "속도", "전압", "전력"을 붙인 것입니다(`CPU Fan 속도`, `+3.3V 전압`, `psys 전력`). 레이블에 이미 그 뜻이 들어 있으면(`power1`, `Vcore Voltage`) 레이블만 쓰고, 두 값의 레이블이 겹치면 칩 이름을 붙입니다.

**처음 발견했을 때 멈춰 있던 팬은 비활성으로 남습니다.** 모니터링 칩은 모든 팬 헤더를 나열하고, 아무것도 연결되지 않은 헤더는 0 rpm을 보고합니다. 팬 센서의 기본 활성 여부는 Home Assistant가 그 엔티티를 처음 등록할 때 한 번만 정합니다. 그때 멈춰 있었거나(예: 유휴 시 멈추는 GPU·케이스 팬) 값이 없던 팬은 나중에 돌기 시작해도 비활성으로 남으니, 필요하면 엔티티 설정에서 켜세요.

**네트워크 인터페이스 기기**(Chirp가 나열한 인터페이스마다 하나, 이름은 `<호스트 이름> <인터페이스>`, 모델은 `Physical interface`, `Bond`, `Bridge`, `VLAN`, `Virtual interface`, 호스트에 연결). unique ID는 `<인스턴스 ID>_net_<인터페이스 id>_<키>`입니다:

| 엔티티 | 키 | 단위·분류 | 기본값 |
|---|---|---|---|
| 수신 속도, 송신 속도 | `rx_rate`, `tx_rate` | 데이터 속도, Chirp의 B/s를 Mbit/s로 표시, measurement; Chirp의 첫 샘플과 카운터 리셋 직후에는 *알 수 없음* | 활성 |
| 누적 수신량, 누적 송신량 | `rx_total`, `tx_total` | 데이터 크기(GB로 표시), total increasing(인터페이스가 생성된 뒤의 커널 누적 카운터) | 진단용, 활성 |
| 링크 | `link` | 연결 이진 센서, Chirp가 링크를 up으로 보고하면 켜짐(operstate `up`, 또는 `unknown`이면서 carrier 있음); 속성 `oper_state`, `kind` | 활성 |
| 링크 속도 | `speed` | 데이터 속도, Mbit/s; 드라이버가 보고하지 않을 때(브리지·VLAN)와 링크가 끊겨 있는 동안 *알 수 없음* | 진단용, 활성 |
| 수신 오류, 송신 오류, 수신 드롭, 송신 드롭 | `rx_errors`, `tx_errors`, `rx_dropped`, `tx_dropped` | total increasing | 진단용, 비활성 |

Chirp는 기본적으로 물리 NIC·본드·브리지·VLAN을 나열하고 `veth*`, `tap*`, Docker 등 가상 장치는 숨깁니다. 서버의 `CHIRP_NET_INCLUDE` / `CHIRP_NET_EXCLUDE`로 바꿀 수 있습니다. 인터페이스마다 기본 활성 엔티티 6개(속도, 누적량, 링크, 링크 속도)와 비활성 4개가 생기므로, 필요 없는 인터페이스는 서버에서 제외하세요.

새 디스크는 다음 조회에서 자동으로 추가됩니다. 서버 시작 후 아직 읽지 못한 디스크(standby·읽기 실패)는 임시 ID `dev_<이름>`만 가지므로, Chirp가 첫 읽기 후 영구 ID를 보고할 때 엔티티를 만듭니다. Chirp 응답에서 사라진 디스크는 사용 불가로 표시되며, 영구히 제거했다면 기기 페이지에서 해당 기기를 삭제하세요. 호스트 기기는 삭제할 수 없습니다.

### 호스트 지표: 제공 조건과 관점(scope)

호스트 지표는 이를 보고하는 Chirp 서버가 필요합니다. 이전 버전 서버는 이 값을 보내지 않으며, 그때는 해당 엔티티를 하나도 만들지 않습니다(오류 없음). 서버가 전혀 읽지 못한 섹션(예: RAPL·hwmon 전력 측정원이 없음)도 만들지 않습니다. 서버 업데이트 등으로 데이터가 나타나면 엔티티가 자동으로 추가됩니다. Chirp가 읽지 못한 개별 값은 *알 수 없음*으로 표시합니다. 나중에 섹션 전체나 인터페이스·팬·전압·전력 측정원이 사라지면 해당 엔티티는 사용 불가가 됩니다. 사라진 인터페이스·디스크 기기는 기기 페이지에서 삭제할 수 있고(나중에 다시 나타나면 엔티티를 다시 만듭니다), 남은 팬·전압·전력 엔티티는 통합을 다시 불러온 뒤 삭제할 수 있습니다.

**관점(호스트 또는 컨테이너).** Chirp는 흔히 컨테이너(Proxmox LXC, Docker)에서 실행됩니다. 이때 메모리·부하·네트워크 값은 **호스트**(컨테이너에 마운트한 호스트의 `/proc`·`/sys`를 읽거나, 컨테이너가 아닌 경우)에서 오거나 **컨테이너** 자신의 관점에서 옵니다. LXC라면 컨테이너 한도(예: RAM 512 MB, CPU 1개)와 컨테이너 자신의 `eth0`일 수 있습니다. 메모리·부하·네트워크 엔티티마다 `scope` 속성(`host` 또는 `container`)이 있고, 진단용 **지표 관점** 센서가 이를 요약합니다(섹션마다 다르면 `mixed`). 관점이 바뀌어도 엔티티 이름은 바뀌지 않습니다. `container`로 나오는데 호스트 값을 원한다면 Chirp 배포 안내([호스트 지표](https://github.com/eigger/chirp/blob/master/docs/deploy.md#host-metrics-memory-load-network))대로 호스트 마운트를 추가하세요. 컨테이너 관점 엔티티도 호스트 관점과 같은 기본 활성 설정을 쓰므로, 나중에 호스트 관점으로 바뀌어도 비활성 상태로 남지 않습니다. 전력·팬·전압은 어느 경우든 호스트 하드웨어 센서에서 읽으며 항상 `scope: host`입니다.

### 건강 상태 사유

디스크별 **건강 상태 사유** 센서(`..._health_reason`)는 문제 원인과 값을 상태값으로 표시합니다. 예를 들어 `온도 높음 (70 °C)`, `재할당된 섹터 (8)`로 표시하고, 여러 사유는 `; `로 연결합니다. 정상으로 돌아오면 `문제 없음`으로 표시합니다. 건강 상태가 계속 `주의`여도 원인이 바뀌면 이 센서의 상태가 바뀌므로 **기록**에서 당시 원인을 확인할 수 있습니다. Recorder가 이 센서를 기록해야 하며 보관 기간과 제외 설정이 적용됩니다. 추가 이전의 원인 내역은 소급 생성되지 않습니다.

표시 문구는 Home Assistant 설정 언어의 번역 파일을 사용하며 번역이 없으면 영어로 표시합니다. 새 언어 설정은 통합을 다시 불러오면 반영됩니다. 아직 번역되지 않은 API 코드는 그대로 표시하고, 전체 원본 코드와 값은 `reasons` 속성에 보존합니다. 상태값이 Home Assistant의 255자 제한을 넘으면 말줄임표로 줄입니다. 판정을 받지 못하고 사유도 없으면 *알 수 없음*, 주의·위험인데 사유가 없으면 `주의 (사유 미보고)`·`위험 (사유 미보고)`로 표시합니다.

`reasons` 속성은 `code`와 선택적 `value`를 가진 객체 목록입니다. 코드는 Chirp API의 값입니다: `smart_failed`, `nvme_critical_warning`, `spare_below_threshold`, `reallocated_sectors`, `pending_sectors`, `offline_uncorrectable`, `media_errors`, `wear_high`, `temperature_high`, `not_read`. Chirp의 판정이 `unknown`(디스크를 읽지 못함, 예: `not_read`)이면 건강 상태 센서는 별도 옵션 대신 Home Assistant 고유의 *알 수 없음* 상태가 되고, `reasons` 속성이 이유를 알려 주며, SMART 문제 센서도 *알 수 없음*이 되어 문제로 보고하지 않습니다.

## 사용 예시

```yaml
action: button.press
target:
  entity_id: button.pve_refresh_smart_data
```

실제 설치에서 생성된 엔티티를 선택하세요. Chirp는 읽기 요청을 대기열에 넣고(HTTP 202) 백그라운드에서 실행하므로, 통합은 5초 간격으로 최대 6회 상태를 조회하고 디스크의 읽은 시각이 바뀐 뒤 더 이상 변하지 않으면 바로 멈춥니다. 다시 누르면 조회를 하나 더 늘리지 않고 처음부터 다시 시작합니다. Chirp는 새로고침 요청 횟수를 제한(HTTP 429)하며, 통합은 이를 성공으로 처리하고 데이터를 한 번 갱신합니다.

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
- Chirp에 연결할 수 없으면 엔티티는 실패 2회까지 마지막 값을 유지하고, 연속 3회째 실패하면 다음 성공 때까지 사용할 수 없음이 됩니다. 연속 조회 오류 센서는 그동안에도 사용 가능하며 다음 성공 시 0으로 돌아갑니다. API 키가 거부되면 엔티티가 바로 사용할 수 없음이 되고 Home Assistant의 재인증을 시작합니다.
- **연결 불가**: 주소·포트·HTTPS 스위치를 확인하고(자체 서명 인증서라면 **SSL 인증서 확인**을 끄세요) 브라우저에서 `http://<주소>:<포트>/health`를 열어 보세요. 주소 칸에는 URL이 아니라 호스트 이름·IPv4·IPv6 주소만 입력합니다. IPv6 zone ID(`%eth0`)는 지원하지 않습니다.
- **인증 오류**: Chirp 대시보드의 **설정 → API 키**에서 키를 다시 복사하세요(누군가 재발급하면 바뀝니다). 재인증 중 다른 Chirp 인스턴스의 키는 거부됩니다.
- API 버전: 이 버전은 Chirp API 버전 1을 지원합니다. 더 새로운 버전이 보고되면 경고를 한 번 기록하고 알려진 필드는 계속 사용합니다.
- **메모리·네트워크 값이 너무 작아 보임**(예: RAM 512 MB, `eth0`만 표시): `scope` 속성이나 **지표 관점** 센서를 확인하세요. `container`는 Chirp가 자기 컨테이너만 본다는 뜻입니다. [호스트 지표: 제공 조건과 관점(scope)](#호스트-지표-제공-조건과-관점scope)을 참고하세요.
- 이슈 보고서에서 API 키·호스트 이름·IP·디스크 시리얼 번호를 제거하세요. 진단 정보는 이를 자동으로 가리며, 인터페이스 이름에 들어 있는 MAC 주소(`enx…`, `wlx…`)도 가립니다.
- 테스트는 실제 Home Assistant와 모의 HTTP 응답을 사용하며 실제 Chirp 서버를 보증하지 않습니다.

## 센서 그룹 선택

처음 설정할 때 **CPU, RAM·스왑, 디스크·SMART, 네트워크, 하드웨어, 파일시스템·ZFS** 체크박스로 추가할 Home Assistant 엔티티를 선택합니다. 이후 **설정 → 기기 및 서비스 → Chirp → 구성**에서 조회 주기와 함께 변경하거나 **재구성**에서 서버 주소와 함께 바꿀 수 있습니다. 기존 설치는 모든 그룹이 선택된 것으로 처리합니다.

그룹 선택을 해제하면 해당 그룹의 새 엔티티를 추가하지 않고 기존 엔티티를 비활성화합니다. 다시 선택하면 그룹을 끄기 전에 활성화했던 엔티티를 복원하며, 엔티티 ID·사용자 지정 이름·사용자가 개별 비활성화한 설정을 보존합니다. 기본 비활성 엔티티는 자동으로 켜지지 않습니다. 부팅 시각·연속 조회 오류·지표 관점은 진단을 위해 유지합니다. 이 선택은 HA 엔티티에 적용되며 Chirp 서버의 자체 수집 주기는 바꾸지 않습니다.

### 추가 센서

| 센서 | 기본값·제공 조건 |
|---|---|
| 가용 메모리 | 활성; 기존 API `memory.availableBytes`; GiB, scope 속성 |
| 스왑 사용량·전체량 | 비활성; 스왑이 있는 경우만; GiB |
| I/O 대기율 | 서버가 `load.ioWaitPercent`를 제공하면 활성; %, scope·CPU 개수 속성 |
| 하드웨어 온도 | `sensors[].id`별 기본 비활성. 안정적인 ID가 없는 이전 서버에서는 생성하지 않음 |
| 마지막 SMART 정상 수집 | 디스크별 진단 타임스탬프, 활성; 대기·읽기 실패 중에도 마지막 정상 시각 유지 |
| SMART 수집 문제 | 진단 문제 이진 센서, 활성; 읽기 오류가 있으면 켜짐. 아직 읽지 않은 디스크는 알 수 없음 |
| SMART 읽기 오류 | 진단 열거형, 비활성; 없음·장치 열기 실패·시간 초과·해석 오류 |
| 대기 모드 | 진단 이진 센서, 비활성; 잠든 디스크를 수집 장애로 취급하지 않음 |
| 파일시스템 사용률·가용 용량 | 설정한 경로별 활성; 사용량·전체 용량은 비활성 |
| ZFS 풀 건강 상태·사용률 | 풀 GUID별 활성; 사용량·전체·여유 용량은 비활성 |

I/O 대기율·안정적인 온도 ID·스토리지 필드는 [서버 PR #7](https://github.com/eigger/chirp/pull/7)의 API 확장이 필요합니다. 가용 메모리·SMART 진단은 이전 서버에서도 동작합니다. 선택적 배열이 없으면 엔티티를 생성하지 않습니다. 한 번 발견한 항목이 사라지면 사용 불가, 다시 나타나면 같은 ID로 복구합니다. 개별 값이 읽히지 않으면 알 수 없음입니다. ZFS 건강 상태는 `ONLINE`, `DEGRADED` 등 서버 원본 상태를 표시합니다.

파일시스템·ZFS 수집은 서버에서 별도로 켭니다. Chirp에 `CHIRP_FILESYSTEM_PATHS=/,/data`, `CHIRP_ZFS_ENABLED=true` 등을 설정하고 재시작하세요. 컨테이너에서 호스트 경로를 읽으려면 명시적인 읽기 전용 루트 마운트와 `CHIRP_HOST_ROOT`도 필요하며, 그렇지 않으면 파일시스템 관점은 컨테이너입니다. [서버 API 계약](https://github.com/eigger/chirp/blob/codex/host-storage-api/docs/api.md#additional-host-and-storage-metrics)을 참고하세요. ZFS 풀 여유 용량은 데이터셋 가용 공간과 다릅니다. 범용 하드웨어 온도에 SMART 디스크 온도와 중복되는 값이 포함될 수 있으므로 필요한 항목만 활성화하세요.
