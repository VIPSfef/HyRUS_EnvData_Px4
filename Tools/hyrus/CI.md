# 외부 모듈·PX4 포크의 두 빌드 기준과 호환성 검사

외부 모듈 저장소는 센서·진단 모듈, 테스트, 버전 지정과 빌드 도구를 관리합니다. MAVLink 연결은 `VIPSfef/Firmware`에서 관리합니다. Simulink R2026b용 안정판과 공식 main 추적판은 서로 다른 프로필·작업본으로 검사합니다.

| 프로필 | 공식 PX4 기준 | 포크 브랜치 | 버전 지정 파일 |
| --- | --- | --- | --- |
| `r2026b` | `v1.16.1` 릴리스 태그 | `hyrus/r2026b` | `Tools/hyrus/profiles/r2026b.json` |
| `main` | 공식 `main`의 기록된 커밋 | `hyrus/mavlink` | `Tools/hyrus/project.json` |

`--profile`을 생략하면 기존 동작인 `main`을 사용합니다. R2026b 검증은 반드시 `--profile r2026b`를 지정합니다. 공식 main 검사가 성공해도 Simulink용 안정판 버전은 바뀌지 않습니다.

## 직접 빌드와 이 문서의 검증 경로

일반 빌드는 README의 두 저장소 준비 절차와 Tools/hyrus/build.sh를 사용합니다. 이 스크립트는 현재 지정한 PX4 작업본에 CMake configure/build를 실행하며 Git 커밋을 바꾸지 않습니다. Python은 PX4 내부 코드 생성의 의존성이지만 우리 Python 준비·검증 도구를 직접 호출할 필요는 없습니다.

이 문서는 두 프로필의 **고정 조합 검증**을 설명합니다. firmware.py prepare는 선택한 manifest의 포크 커밋으로 전용 작업본을 준비하므로 임의의 사용자 커스텀 펌웨어를 유지한 채 검사하는 경로가 아닙니다. Simulink가 생성한 제어 코드나 사용자 변경이 있는 작업본에는 prepare/validate를 실행하지 않습니다. 해당 작업본에는 직접 빌드 경로와 모델 자체의 검증을 사용합니다.

Portable addon 태그 hyrus-mavlink-addon-v1은 MAVLink 확장 여섯 파일의 순변경을 담습니다. 추적 브랜치는 추가로 표준 HYGROMETER_SENSOR 습도 단위 수정 한 파일을 별도 커밋으로 관리합니다. 고정 조합 검증의 변경 허용 목록은 이 둘을 포함한 일곱 MAVLink 파일입니다. 이 단위 수정은 portable addon에 자동 포함하지 않습니다.

## 버전 지정

각 프로필의 manifest는 다음 값을 관리합니다.

| 키 | 의미 |
| --- | --- |
| `upstream_url` | 공식 PX4 저장소 |
| `upstream_branch` 또는 `upstream_ref` | main의 추적 브랜치 또는 안정판의 정확한 릴리스 태그 |
| `upstream_commit` | 현재 포크 변경을 비교하는 공식 기준 SHA |
| `fork_url`, `fork_branch` | MAVLink 변경을 관리하는 포크와 브랜치 |
| `px4_commit` | 실제 빌드할 포크의 전체 SHA |
| `firmware_target` | 대상 보드의 빌드 타깃 |

`prepare`는 포크 브랜치의 최신 끝이 아니라 `px4_commit`을 체크아웃합니다. 공식 기준이 포크의 조상이고 두 커밋 사이의 변경이 허용한 MAVLink 경로에만 있는지 검사합니다. main은 기준 커밋이 공식 main 이력에 있는지, r2026b는 기준 SHA가 공식 `v1.16.1` 태그를 실제로 가져와 해석한 커밋과 정확히 같은지 확인합니다. 태그 이름만 같거나 main의 자손이라는 이유로 안정판을 승인하지 않습니다. `git apply`로 적용할 별도 패치는 없습니다.

## 빌드 순서

1. 외부 모듈 파일과 버전 지정 형식을 검사합니다.
2. 포크를 전체 이력으로 복제하거나, 지정한 깨끗한 전용 작업본을 사용합니다.
3. 지정한 포크 커밋과 그 커밋에 기록된 하위 모듈을 준비합니다.
4. 공식 기준과의 관계·변경 범위, 센서 장치 ID 충돌, PX4/NuttX 이력을 검사합니다.
5. Git 동작 회귀 테스트와 native 센서·진단·포크 스트림 테스트를 실행합니다.
6. build.sh의 직접 CMake 경로에 EXTERNAL_MODULES_LOCATION을 전달해 ARM 펌웨어 전체를 빌드합니다.
7. 실제 생성 MAVLink 헤더로 패킷을 검사하고, 최종 ELF의 센서 명령과 파라미터 포함 여부를 확인합니다.
8. 소스 커밋·하위 모듈·통합 변경·펌웨어 식별 정보를 기록하고 결과를 모읍니다.

센서 드라이버는 공식 외부 모듈 API로 빌드합니다. MAVLink 연결은 포크가 관리하는 변경입니다. 보드 설정, 센서 장치 등록부, 정상 부팅 및 비행 제어 파일은 HyRUS를 위해 변경하지 않습니다. 센서 자동 시작은 SD 카드 `extras.txt` 예제를 사용합니다.

## R2026b 고정 조합의 로컬 검증

Ubuntu 또는 WSL Ubuntu의 Linux 파일시스템에서 실행합니다. 시작 위치는 외부 모듈 저장소 루트입니다. 검증 보고서는 커밋된 깨끗한 외부 모듈 작업본을 요구합니다.

```sh
HYRUS_PX4_DIR="$HOME/src/PX4-HyRUS-R2026b-Verified"
python3 Tools/hyrus/firmware.py prepare --profile r2026b --px4-dir "$HYRUS_PX4_DIR"
bash "$HYRUS_PX4_DIR/Tools/setup/ubuntu.sh" --no-sim-tools
python3 Tools/hyrus/validate.py --profile r2026b --px4-dir "$HYRUS_PX4_DIR" --jobs 6
```

공식 setup 스크립트는 `sudo`로 개발 의존성을 설치합니다. 선택한 포크의 requirements.txt가 필요한 Python 패키지 버전을 지정합니다. main을 검사할 때는 위 명령의 프로필을 `main`으로 바꾸고 별도 작업 폴더를 사용합니다.

경로 옵션을 생략하면 다음처럼 서로 겹치지 않는 폴더를 사용합니다.

| 용도 | main | r2026b |
| --- | --- | --- |
| PX4 소스 | `build/px4/` | `build/px4-r2026b/` |
| native 테스트 캐시 | `build/hyrus-native/` | `build/hyrus-native-r2026b/` |
| 보고서·펌웨어·로그 | `build/hyrus-ci/` | `build/hyrus-ci-r2026b/` |

기존 패치 방식 작업본의 수정 사항을 이 도구가 지우거나 포크 커밋으로 바꾸지 않습니다. 그런 작업본이 있다면 보존하고 새 전용 경로를 사용하세요. 하위 모듈도 기록된 커밋과 전체 이력을 사용합니다. 버전 문자열만으로 소스 조합을 판정하지 않습니다.

펌웨어 원본은 PX4 작업본의 `build/px4_fmu-v6c_default/px4_fmu-v6c_default.px4`에 생깁니다. 검증 결과는 위 표의 해당 프로필 결과 폴더에 복사됩니다. `validation.json`에는 프로필, 공식 ref, 외부 모듈·포크·공식 커밋, 실제 펌웨어 SHA-256을 기록합니다. 검증이 시작된 뒤 실패하면 비정상 종료와 실패한 보고서를 남깁니다. 준비·검증 스크립트는 원격 브랜치나 기체를 변경하지 않습니다.

R2026b 프로필의 성공은 **PX4 v1.16.1에 센서와 MAVLink를 포함한 ARM 빌드**의 성공입니다. MATLAB에서 실제 모델을 생성한 검사, Simulink의 자동 배포, 기체 부팅·비행 시험을 대신하지 않습니다.

## 공식 main 업데이트 검사

`hyrus-ci.yml`은 외부 모듈 `main` 푸시, PR, 수동 실행에서 `main`과 `r2026b` 조합을 독립된 matrix job으로 검사합니다. 결과 artifact 이름에도 프로필이 들어갑니다. `hyrus-upstream.yml`은 매일 **03:17 UTC / 12:17 한국 시간**과 수동 실행으로 공식 main만 확인합니다. 안정판 manifest와 포크 브랜치는 이 업데이트 대상이 아닙니다.

업데이트 검사는 다음 순서입니다.

1. 현재 외부 모듈 커밋과 포크 커밋을 기준으로 전용 작업본을 준비합니다.
2. 최신 공식 main을 가져와 임시 포크 작업본에 Git으로 병합합니다.
3. 병합 충돌이나 허용 범위 밖 변경이 있으면 실패 결과를 보관하고 중단합니다.
4. 포크 후보를 만들고, 외부 모듈의 분리된 후보에서 `upstream_commit`과 `px4_commit`만 갱신합니다.
5. 같은 준비·native 테스트·ARM 빌드·실제 MAVLink 검사를 실행합니다.
6. 정확히 검사한 포크 후보와 외부 모듈 후보를 각각 Git bundle로 보관합니다.

원격 브랜치와 기본 브랜치의 manifest는 이 과정에서 갱신하지 않습니다. 후보를 검토한 뒤 포크 커밋을 먼저 게시하고 외부 모듈의 manifest 변경을 반영해야 합니다. 포크의 새 커밋이 원격에 없으면 일반 빌드가 해당 커밋을 가져올 수 없습니다.

워크플로는 `contents: read`로 두 공개 저장소를 읽고 결과 artifact를 보관합니다. 다른 저장소를 수정하는 토큰이나 Actions의 PR 승인 권한을 요구하지 않습니다. 자동 PR 생성·원격 병합·기체 업로드를 수행하는 단계는 없습니다.

후보를 로컬에서 확인하려면 **일회용 깨끗한 외부 모듈 복제본**에서 실행합니다.

```sh
HYRUS_PX4_DIR="$HOME/src/PX4-HyRUS-Candidate"
python3 Tools/hyrus/upstream.py prepare \
  --px4-dir "$HYRUS_PX4_DIR" --output build/hyrus-upstream
# candidate.json의 changed=true, state=prepared일 때 이어서 실행합니다.
bash "$HYRUS_PX4_DIR/Tools/setup/ubuntu.sh" --no-sim-tools
python3 Tools/hyrus/validate.py \
  --px4-dir "$HYRUS_PX4_DIR" --output build/hyrus-upstream --jobs 6
python3 Tools/hyrus/upstream.py package \
  --px4-dir "$HYRUS_PX4_DIR" --output build/hyrus-upstream
```

검사 결과의 `candidate.json`에는 외부 모듈 기준 `base`, 포크 기준 `fork_base`, 새 공식 기준 `upstream`, 포크 후보 `fork_candidate`, 외부 모듈 후보 `candidate`를 기록합니다. `candidate.bundle`은 외부 모듈 manifest 변경, `firmware-candidate.bundle`은 포크 병합 후보를 담습니다.

공식 main이 이미 반영되어 있다면 후보를 새로 만들지 않습니다. 준비·검증 로그, 후보 보고서, 펌웨어, 통과한 Git bundle은 GitHub artifact에 14일 동안 보관합니다. Git 병합과 빌드 성공은 실제 I2C 동작·SITL·비행 시험 또는 모든 upstream 동작 변화의 검증을 뜻하지 않습니다.
