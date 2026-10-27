# HyRUS_EnvData_Px4

PX4에서 I2C 환경 센서를 읽고 측정값을 MAVLink 메시지로 내보내는 펌웨어 확장입니다. SHTC3 드라이버, I2C 진단 코어, SENS_ATMOS 송신 스트림, PX4 버전별 오버레이와 검증 기록을 관리합니다.

서버 전송은 [HyRUS_EnvData_Router](https://github.com/VIPSfef/HyRUS_EnvData_Router)가 담당합니다. 이 저장소는 HTTP·UDP 서버 송신기와 PC 라우터를 포함하지 않습니다. 수신 측과 맞춰야 할 메시지 ID·단위·유효성은 [MAVLink 연결 규약](https://github.com/VIPSfef/HyRUS_EnvData_Router/blob/main/docs/PX4_MAVLINK_CONTRACT.md)을 기준으로 확인합니다.

```text
I2C 센서 → PX4 드라이버/uORB → MAVLink carrier
                                     ↓
                            HyRUS_EnvData_Router → HTTP/UDP 서버
```

## 구성과 펌웨어 적용

- `src/px4/shtc3`: SHTC3 측정과 CRC·프로토콜 코어
- `src/px4/shtc3_probe`: 제품 ID·버스·CRC 진단
- `src/px4/sens_atmos`: SENS_ATMOS 송신 스트림과 dialect
- `support/px4`: 대상 PX4/MAVLink 커밋, 패치, 해시 검증과 오버레이 적용 도구

실물 Pixhawk 6C의 PX4 1.16.0 구성은 [SHTC3 측정·송신 안내](support/px4/pixhawk6c-v1.16-weather/README.md)를 따릅니다. [전체 오버레이 안내](support/px4/README.md)는 다른 기준 커밋과 SITL 구성을 함께 설명합니다. 버전별 manifest를 혼용하지 마세요.

기존 Router 저장소의 `src/px4`와 `support/px4`를 같은 상대 경로로 분리했기 때문에, manifest의 패치 경로와 SHA256은 그대로 유지됩니다. 실제 PX4 checkout과 비행 제어기에는 이 분리 작업으로 변경을 가하지 않았습니다. 패치 검사·적용·펌웨어 빌드·플래시는 각 안내의 별도 절차입니다.

## 장치 없이 검증

CMake 3.21 이상, C++ 컴파일러, Python 3, Git과 Ninja가 필요합니다.

```sh
cmake -S . -B build/native -G Ninja -DCMAKE_BUILD_TYPE=Release
cmake --build build/native
ctest --test-dir build/native --output-on-failure
```

이 검증은 SHTC3 프로토콜, 진단 코어, MAVLink 스트림 stub, 임시 Git 저장소에 대한 오버레이 안전성 테스트만 실행합니다. PX4 전체 펌웨어 빌드나 하드웨어 검증을 대신하지 않습니다.

## 온습도 관측을 시험하기

측정 이후의 PC 수신, 서버 전송, 시험 서버 실행은 [Router 실행 안내](https://github.com/VIPSfef/HyRUS_EnvData_Router#readme)와 [서버 API](https://github.com/VIPSfef/HyRUS_EnvData_Router/blob/main/docs/SERVER_API.md)를 참고하세요. WSL loopback 수신기를 사용하는 경우 송신·수신의 네트워크 환경을 맞춰야 합니다.

분리된 소스에는 아직 별도 프로젝트 전체 라이선스가 지정되지 않았습니다. PX4 등 기존 코드의 저작권 표시와 라이선스는 각 파일에 유지됩니다.
