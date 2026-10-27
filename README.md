# HyRUS EnvData PX4

커스텀 UAV 서베이어의 SHTC3 I2C 온습도 센서를 읽는 **PX4 외부 모듈**입니다. 센서·진단 코드는 이 저장소에서, MAVLink 송신 확장은 [VIPSfef/Firmware의 hyrus/mavlink](https://github.com/VIPSfef/Firmware/tree/hyrus/mavlink)에서 관리합니다. 결과물은 두 소스를 함께 컴파일한 하나의 PX4 펌웨어입니다.

PC에서 MAVLink를 받아 HTTP·UDP로 서버에 전달하는 기능은 별도 [HyRUS_EnvData_Router](https://github.com/VIPSfef/HyRUS_EnvData_Router)가 담당합니다.

## 사용할 빌드 경로

| 목적 | 사용할 경로 |
| --- | --- |
| 제공된 포크 또는 직접 관리하는 PX4를 빌드 | 두 저장소와 하위 모듈을 준비한 뒤 build.sh 또는 CMake 직접 실행 |
| 기록된 커밋 조합의 테스트·검증 보고서 생성 | firmware.py prepare와 validate.py |
| 다른 PX4 버전·커스텀 브랜치에 MAVLink 확장만 이식 | 아래 addon 태그의 단일 커밋을 cherry-pick한 뒤 직접 빌드 |

**build.sh는 지정한 PX4 작업본을 그대로 빌드합니다.** Git 브랜치·커밋을 옮기거나 소스를 다운로드·수정하지 않습니다. project.json의 보드 타깃을 기본값으로 사용하며 --target으로 바꿀 수 있습니다.

반면 firmware.py prepare는 재현 가능한 검증을 위해 project.json의 포크 커밋을 선택합니다. 다른 커스텀 펌웨어를 그대로 빌드할 때는 직접 빌드 경로를 사용하세요.

## 처음 받기와 개발 환경 준비

Ubuntu 24.04 또는 WSL2 Ubuntu의 **Linux 파일시스템**에서 실행합니다. 아래는 새 폴더에 두 저장소를 받는 순서입니다.

~~~sh
sudo apt update
sudo apt install -y git

mkdir -p "$HOME/src"
cd "$HOME/src"

git clone https://github.com/VIPSfef/HyRUS_EnvData_Px4.git
git clone --filter=blob:none --single-branch --branch hyrus/mavlink \
  https://github.com/VIPSfef/Firmware.git PX4-HyRUS-Fork

HYRUS_PX4_DIR="$HOME/src/PX4-HyRUS-Fork"

# 공식 태그는 PX4 버전 정보 생성에 사용합니다.
git -C "$HYRUS_PX4_DIR" fetch --no-recurse-submodules --filter=blob:none --tags \
  https://github.com/PX4/PX4-Autopilot.git main
git -C "$HYRUS_PX4_DIR" submodule update --init --recursive

# 개발 환경을 처음 준비할 때 실행합니다.
bash "$HYRUS_PX4_DIR/Tools/setup/ubuntu.sh" --no-sim-tools

cd "$HOME/src/HyRUS_EnvData_Px4"
~~~

개발 의존성은 Git, CMake·Ninja·Make, ARM GCC·newlib, 호스트 C/C++ 컴파일러, Python 3와 PX4 요구 패키지입니다. 공식 ubuntu.sh가 이를 설치하며 sudo를 사용할 수 있습니다.

**Python은 PX4 자체의 빌드 의존성**입니다. CMake가 MAVLink·uORB·파라미터 코드 생성과 펌웨어 패키징에 사용합니다. 센서가 기체에서 Python으로 실행되는 것은 아닙니다. 이 저장소의 firmware.py·validate.py는 추가 준비·검증 도구이므로 직접 빌드에서는 실행하지 않아도 됩니다.

## 스크립트로 빌드

외부 모듈 저장소 루트에서 실행합니다.

~~~sh
bash Tools/hyrus/build.sh \
  --px4-dir "$HOME/src/PX4-HyRUS-Fork" \
  --jobs 6
~~~

스크립트 내부 순서는 **도구·하위 모듈 확인 → 기존 CMake 캐시 확인 → CMake configure → CMake build → 펌웨어 경로 출력**입니다. 다른 소스·외부 모듈·보드 타깃으로 만든 캐시를 잘못 재사용하면 중단합니다.

| 옵션 | 의미 |
| --- | --- |
| --px4-dir PATH | 빌드할 PX4 Git 작업본. 생략하면 이 저장소의 build/px4 |
| --target BOARD | PX4 보드 타깃. 기본값은 project.json의 px4_fmu-v6c_default |
| --build-dir PATH | 출력 폴더. 기본값은 PX4경로/build/보드타깃 |
| --jobs N | 병렬 작업 수. 생략하면 사용 가능한 CPU 수 |
| --configure-only | CMake 설정까지만 실행 |
| --help | 사용법 표시 |
| -- -DNAME=VALUE | 추가 CMake 정의 전달. 소스·외부 모듈·타깃 덮어쓰기는 허용하지 않음 |

설정을 바꿀 때는 다음처럼 전달할 수 있습니다.

~~~sh
bash Tools/hyrus/build.sh --px4-dir "$HOME/src/PX4-HyRUS-Fork" \
  -- -DHYRUS_MAVLINK=OFF
~~~

CMake 옵션은 빌드 폴더에 저장됩니다. 위에서 확장을 껐다면 같은 폴더에서 다시 켤 때 `-- -DHYRUS_MAVLINK=ON`을 명시하세요. 옵션을 생략하면 이전 설정을 유지합니다.

소스를 수정한 뒤에도 같은 빌드 명령으로 증분 빌드할 수 있습니다. 메모리가 부족하면 병렬 작업 수를 낮추세요. 다른 보드는 해당 보드가 센서 연결과 PX4 외부 모듈 API를 지원하는지 별도로 확인해야 합니다.

## CMake로 직접 빌드

스크립트가 수행하는 핵심 명령입니다.

~~~sh
HYRUS_PX4_DIR="$HOME/src/PX4-HyRUS-Fork"
HYRUS_MODULE_DIR="$HOME/src/HyRUS_EnvData_Px4"

cmake -S "$HYRUS_PX4_DIR" \
  -B "$HYRUS_PX4_DIR/build/px4_fmu-v6c_default" \
  -G Ninja \
  -DCONFIG=px4_fmu-v6c_default \
  -DCMAKE_BUILD_TYPE=MinSizeRel \
  -DEXTERNAL_MODULES_LOCATION="$HYRUS_MODULE_DIR"

cmake --build "$HYRUS_PX4_DIR/build/px4_fmu-v6c_default" --parallel 6
~~~

출력은 다음 파일입니다.

~~~text
~/src/PX4-HyRUS-Fork/build/px4_fmu-v6c_default/px4_fmu-v6c_default.px4
~~~

이 단계는 펌웨어 파일을 생성합니다. 별도의 cmake --install 단계는 없으며 기체 업로드는 별도 작업입니다.

## MAVLink 확장이 추가하는 것

- 기존 펌웨어가 선택한 MAVLink dialect를 유지하고, SENS_ATMOS를 제공하는 ASLUAV 정의를 함께 포함한 wrapper를 생성합니다.
- 기존 HYGROMETER_SENSOR 기본 스트림을 유지하면서 SENS_ATMOS 스트림을 등록하고 USB/config·onboard 기본 송신에 추가합니다.
- 보드 설정, 비행 제어, 정상 부팅 코드를 변경하지 않습니다. 센서는 외부 모듈로 연결합니다.
- 포크 자체의 HYRUS_MAVLINK 옵션 기본값은 꺼짐입니다. 이 외부 모듈을 연결하면 기본으로 켜며, 명시한 -DHYRUS_MAVLINK=OFF를 존중합니다.

다른 펌웨어로 옮기는 addon 태그는 MAVLink 경로 여섯 파일의 순수 추가분이며 기존 HYGROMETER_SENSOR 처리를 바꾸지 않습니다. 검증용 hyrus/mavlink 추적 브랜치에는 이와 별개로 **HYGROMETER_SENSOR의 습도 단위를 공식 MAVLink 규격인 0.01 %RH에 맞추는 수정**도 유지합니다. 이 수정은 별도 커밋이며 addon 태그에 포함하지 않습니다. 다른 버전에는 해당 단위 문제가 있는지 확인한 뒤 별도로 반영합니다.

기존 PX4 위에 필요한 송신 기능을 추가하는 구조입니다. 다만 **다른 PX4 버전의 API까지 자동으로 호환된다는 뜻은 아닙니다.** uORB 필드, 스트림 등록 위치, CMake 또는 메시지 정의가 바뀌면 이식 수정과 빌드 검사가 필요합니다. ArduPilot 등 다른 펌웨어 계열은 별도 구현 대상입니다.

## 다른 PX4 버전·커스텀 브랜치에 확장만 이식

[포크의 hyrus-mavlink-addon-v1 태그](https://github.com/VIPSfef/Firmware/tree/hyrus-mavlink-addon-v1)는 공식 기준에 대한 **MAVLink 추가분만 담은 단일 커밋**을 가리킵니다. 사용자가 관리하는 PX4 브랜치에서 새 통합 브랜치를 만든 뒤 그 커밋만 가져옵니다.

아래 명령은 **사용할 PX4 저장소의 원하는 브랜치를 이미 선택하고, 변경 사항을 커밋한 상태**에서 실행합니다.

~~~sh
# 사용자 PX4 저장소 안에서 실행
git status --short
git switch -c surveyor-integration

git fetch https://github.com/VIPSfef/Firmware.git \
  refs/tags/hyrus-mavlink-addon-v1
git cherry-pick FETCH_HEAD

git submodule update --init --recursive

bash "$HOME/src/HyRUS_EnvData_Px4/Tools/hyrus/build.sh" \
  --px4-dir "$PWD" \
  --target px4_fmu-v6c_default \
  --jobs 6
~~~

git status --short에 변경이 표시되면 먼저 정리하고 진행하세요. Cherry-pick 충돌이 발생하면 그 버전의 API에 맞춰 해결하거나 git cherry-pick --abort로 이식 시도를 취소합니다.

**추가 기능만 옮기려는 경우 git merge hyrus/mavlink를 사용하지 않습니다.** 추적 브랜치 전체를 병합하면 그 브랜치가 포함한 공식 PX4 업데이트도 함께 들어옵니다. Addon 태그를 cherry-pick하면 사용자가 선택한 펌웨어 이력을 유지하면서 해당 커밋의 변경만 적용합니다.

이식 이후에는 사용자가 선택한 펌웨어의 원본 브랜치를 surveyor-integration에 병합해 업데이트합니다. MAVLink 확장 커밋을 유지하고 다시 빌드·시험합니다. 새 addon 버전을 적용할 때는 이미 들어간 확장과의 차이를 검토해야 합니다.

## 고정된 조합 검증과 자동 업데이트 검사

제공된 조합을 재현하고 검증 보고서를 만들 때는 외부 모듈 저장소 루트에서 실행합니다.

~~~sh
HYRUS_PX4_DIR="$HOME/src/PX4-HyRUS-Verified"

python3 Tools/hyrus/firmware.py prepare --px4-dir "$HYRUS_PX4_DIR"
bash "$HYRUS_PX4_DIR/Tools/setup/ubuntu.sh" --no-sim-tools
python3 Tools/hyrus/validate.py --px4-dir "$HYRUS_PX4_DIR" --jobs 6
~~~

이 검증은 커밋된 깨끗한 외부 모듈 작업본과 manifest에 기록된 포크를 대상으로 합니다. 임의의 사용자 커스텀 펌웨어를 이 기준으로 자동 승인하지 않습니다. 펌웨어·validation.json·단계별 로그는 외부 모듈 저장소의 build/hyrus-ci/에 모읍니다.

hyrus-upstream.yml은 매일 **12:17 한국 시간**에 공식 main을 현재 포크에 시험 병합하고 호환성을 검사합니다. 실패하면 현재 기준을 유지하고, 성공하면 포크와 외부 모듈 후보를 Git bundle로 보관합니다. 원격 브랜치 반영은 검토 후 진행합니다. 검사 범위와 명령은 [CI.md](Tools/hyrus/CI.md)에 설명합니다.

## 센서 시작

자동 시작 예제는 외부 I2C **버스 2**, 주소 **0x70**의 SHTC3 한 개를 대상으로 합니다. 실제 보드·배선에 맞춰 버스 번호를 확인하세요. SENS_EN_SHTC3 기본값은 0이며 예제는 값이 1일 때만 드라이버를 시작합니다.

sdcard/etc/extras.txt의 내용을 SD 카드의 /fs/microsd/etc/extras.txt에 기존 부팅 명령과 합쳐 넣습니다. 이 방식은 PX4의 rc.sensors를 수정하지 않습니다.

## 소스와 문서

| 위치 | 역할 |
| --- | --- |
| src/drivers/hygrometer/shtc3/ | 센서 측정·복구·uORB 발행 |
| src/systemcmds/shtc3_probe/ | I2C 진단 명령 |
| src/CMakeLists.txt | 공식 외부 모듈 등록과 MAVLink 확장 선택 |
| Tools/hyrus/build.sh | 직접 CMake 빌드 |
| Tools/hyrus/project.json | 검증할 공식 기준·포크·보드 지정 |
| test/hyrus/ | 센서·스트림·패킷 검사 |
| 포크의 src/modules/mavlink/ | 선택 가능한 MAVLink 확장 |

- [전체 빌드·데이터·실패 흐름](docs/architecture.md)
- [포크 갱신과 브랜치·addon 태그의 역할](docs/fork-comparison.md)
- [자동 검사 운영 절차](Tools/hyrus/CI.md)
- [PX4 공식 외부 모듈 지침](https://docs.px4.io/main/en/advanced/out_of_tree_modules)
- [PX4 공식 개발 환경](https://docs.px4.io/main/en/dev_setup/dev_env_linux_ubuntu)
