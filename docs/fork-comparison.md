# 기존 Firmware 포크 비교

확인일: **2026-10-27 (한국 시간)**. 이 문서의 “기존 포크”는 [VIPSfef/Firmware](https://github.com/VIPSfef/Firmware)이며 현재 HyRUS 외부 모듈 작업본과 구분합니다.

| 항목 | 확인 결과 |
| --- | --- |
| 기본 브랜치 | `master` |
| 기본 브랜치 커밋 | `a40c9831376f31cb560b2d66c49c2067abd67f8a` |
| 커밋 날짜 | 2018-08-06 |
| 커밋 내용 | `updated submodule src/lib/DriverFramework` |
| 비교한 공식 main | `a743c7b7369873b6530bcd51019477a5fe9659ab` |
| 공식 main 대비 | 포크에만 있는 커밋 0개 / 공식에 추가된 커밋 24,678개 |
| 공식 v1.16.0 대비 | 포크에만 있는 커밋 0개 / 공식에 추가된 커밋 20,128개 |
| 포크 브랜치 수 | 180개 |

GitHub 비교 결과와 로컬 `git rev-list --left-right --count` 결과를 대조했습니다. 기본 `master`는 비교한 공식 main의 조상이며, 이 기본 브랜치에서 HyRUS로 옮겨야 할 독자 커밋은 없습니다.

기존 기본 브랜치에는 `boards/px4/fmu-v6c`, `src/drivers/hygrometer`, `src/modules/mavlink/streams/SENS_ATMOS.hpp` 경로가 없습니다. 현재 Pixhawk 6C용 외부 모듈 빌드는 이 2018년 포크 대신 `Tools/hyrus/project.json`에 고정한 공식 PX4 소스를 사용합니다.

이 비교는 기본 `master`의 이력에 대한 결과입니다. 나머지 179개 브랜치의 독자 변경 유무까지 모두 판정한 것은 아닙니다. 브랜치가 많다는 이유만으로 사용자 변경이 많거나 없다고 단정할 수 없습니다. 비교 과정에서 기존 포크를 갱신·삭제·이름 변경하지 않았습니다.

근거:

- [기존 기본 브랜치의 마지막 커밋](https://github.com/VIPSfef/Firmware/commit/a40c9831376f31cb560b2d66c49c2067abd67f8a)
- [공식 main 기준으로 포크 master 비교](https://github.com/PX4/PX4-Autopilot/compare/a743c7b7369873b6530bcd51019477a5fe9659ab...a40c9831376f31cb560b2d66c49c2067abd67f8a)
- [기존 포크에서 공식 v1.16.0까지의 변경](https://github.com/PX4/PX4-Autopilot/compare/a40c9831376f31cb560b2d66c49c2067abd67f8a...6ea3539157ca358c70a515878b77077af7d4611d)

커밋 수는 위 두 시점의 비교값입니다. 이후 공식 main이 갱신되어도 이 기록 자체의 비교 기준은 바뀌지 않습니다.
