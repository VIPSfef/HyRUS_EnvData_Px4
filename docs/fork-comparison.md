# Firmware 포크의 갱신과 브랜치 역할

기록일: **2026-10-27 (한국 시간)**. 대상은 [VIPSfef/Firmware](https://github.com/VIPSfef/Firmware)입니다. 센서 외부 모듈 저장소 `HyRUS_EnvData_Px4`와 구분합니다.

## 갱신 후 구조

`Firmware/master`를 공식 PX4 `main`의 `a743c7b7369873b6530bcd51019477a5fe9659ab`로 fast-forward했습니다. 갱신 직후 양쪽 커밋과 소스 트리 SHA가 같은 것을 확인했습니다. 기존 이력은 보존했습니다.

| 브랜치 또는 설정 | 역할 |
| --- | --- |
| `Firmware/master` | 공식 코드 동기화용 브랜치 |
| `Firmware/hyrus/mavlink` | 공식 이력 위에 MAVLink 연결과 별도 습도 단위 수정을 유지하는 브랜치 |
| `hyrus-mavlink-addon-v1` 태그 | 다른 PX4 브랜치에 이식할 순수 MAVLink 추가분의 단일 커밋 |
| 외부 모듈의 `project.json: upstream_commit` | 포크 변경을 비교하는 공식 기준 커밋 |
| 외부 모듈의 `project.json: px4_commit` | 실제 펌웨어 빌드에 사용할 포크 커밋 |

MAVLink 스트림·메시지 정의·등록 코드는 포크에서 관리하고, SHTC3 드라이버·진단 명령은 외부 모듈 저장소에서 관리합니다. 고정 조합 검증은 manifest의 전체 SHA를 사용합니다. 직접 CMake 또는 build.sh 빌드는 사용자가 지정한 현재 체크아웃을 사용합니다. 새 공식 main은 별도 병합 후보로 검사합니다.

`master` 동기화와 HyRUS 펌웨어 호환성 검사는 별개입니다. 공식 코드와 포크의 동기화 성공 자체가 외부 센서 모듈의 빌드 성공을 뜻하지 않습니다. 실제 검증 결과는 해당 조합의 `validation.json`과 CI 로그를 확인합니다.

## 다른 펌웨어에 추가분만 이식하는 기준

hyrus/mavlink는 공식 main 이력을 포함한 추적 브랜치입니다. 이를 다른 PX4 버전·커스텀 브랜치에 통째로 병합하면 공식 PX4 업데이트도 함께 들어옵니다.

hyrus-mavlink-addon-v1 태그는 공식 기준 대비 MAVLink 확장만 담은 단일 커밋을 가리킵니다. 다른 PX4 브랜치에는 이 태그를 fetch하고 cherry-pick하여 사용자가 선택한 기반 이력을 유지합니다. 실제 명령은 README에 있습니다. 충돌이 없더라도 해당 버전의 API와 메시지 정의에 대한 빌드·기기 검사는 필요합니다.

Addon은 기존 dialect와 HYGROMETER_SENSOR 기본 동작을 유지하고 SENS_ATMOS를 추가합니다. 추적 브랜치에는 표준 HYGROMETER_SENSOR 습도를 0.01 %RH로 직렬화하는 별도 수정도 있습니다. 이 단위 수정은 addon 태그에서 제외하여 다른 펌웨어의 상태에 맞게 별도로 검토할 수 있습니다.

## 갱신 전 조사 기록

아래 표는 **업데이트 전** 기본 `master`를 비교한 결과이며 현재 브랜치 상태를 나타내지 않습니다.

| 항목 | 갱신 전 확인 결과 |
| --- | --- |
| 기본 브랜치 | `master` |
| 기본 브랜치 커밋 | `a40c9831376f31cb560b2d66c49c2067abd67f8a` |
| 커밋 날짜 | 2018-08-06 |
| 커밋 내용 | `updated submodule src/lib/DriverFramework` |
| 비교한 공식 main | `a743c7b7369873b6530bcd51019477a5fe9659ab` |
| 공식 main 대비 | 포크에만 있는 커밋 0개 / 공식에 추가된 커밋 24,678개 |
| 공식 v1.16.0 대비 | 포크에만 있는 커밋 0개 / 공식에 추가된 커밋 20,128개 |
| 당시 포크 브랜치 수 | 180개 |

GitHub 비교와 로컬 `git rev-list --left-right --count` 결과를 대조했습니다. 갱신 전 `master`는 공식 main의 조상이었으며 옮겨야 할 독자 커밋이 없어 fast-forward할 수 있었습니다. 당시 기본 브랜치에는 `boards/px4/fmu-v6c`, `src/drivers/hygrometer`, `src/modules/mavlink/streams/SENS_ATMOS.hpp` 경로가 없었습니다.

이 조사는 당시 기본 `master`의 이력에 대한 결과입니다. 나머지 179개 브랜치의 독자 변경 유무까지 모두 판정한 것은 아닙니다. 해당 브랜치들을 삭제하거나 이름을 변경하지 않았습니다.

근거:

- [갱신 전 기본 브랜치의 마지막 커밋](https://github.com/VIPSfef/Firmware/commit/a40c9831376f31cb560b2d66c49c2067abd67f8a)
- [이번 동기화의 공식 기준 커밋](https://github.com/PX4/PX4-Autopilot/commit/a743c7b7369873b6530bcd51019477a5fe9659ab)
- [갱신 전 포크와 공식 main의 고정 시점 비교](https://github.com/PX4/PX4-Autopilot/compare/a743c7b7369873b6530bcd51019477a5fe9659ab...a40c9831376f31cb560b2d66c49c2067abd67f8a)
- [갱신 전 포크에서 공식 v1.16.0까지의 변경](https://github.com/PX4/PX4-Autopilot/compare/a40c9831376f31cb560b2d66c49c2067abd67f8a...6ea3539157ca358c70a515878b77077af7d4611d)

커밋 수는 위 고정 시점의 비교값입니다. 이후 브랜치가 갱신되어도 이 기록의 비교 기준은 바뀌지 않습니다.
