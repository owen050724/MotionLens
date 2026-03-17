# MintCam Recorder

OpenCV 기반 실시간 Video Recorder입니다.  
단일 카메라 창에서 **클릭 UI + 단축키**로 녹화/필터/모션/포즈 기능을 제어할 수 있습니다.

---

## 프로젝트 개요

- 기본 요구사항(OpenCV `VideoCapture`, `VideoWriter`, Preview/Record, Space/ESC)을 충족합니다.
- 추가 기능으로 클릭형 상단 컨트롤 바, 모션 감지/자동녹화, Pose 검출, 스냅샷 저장을 제공합니다.
- 카메라 해상도는 `1920x1080`을 요청하며, 장치 미지원 시 가능한 해상도로 동작합니다.

---

## 주요 기능

| 기능 | 설명 |
|---|---|
| 실시간 미리보기 | 카메라 영상을 실시간 표시 |
| 녹화 모드 | `Space` 또는 `REC` 버튼으로 녹화 시작/종료 |
| 녹화 표시 | 녹화 중 빨간 인디케이터(REC) 표시 |
| 필터 | `normal / gray / edge` 순환 전환 |
| 코덱 전환 | `mp4v -> XVID -> MJPG -> avc1` 순환 |
| FPS 조절 | 5~120 범위에서 실시간 조절(녹화 중 변경 제한) |
| 좌우 반전 | 미리보기/녹화 화면 동시 반영 |
| 모션 감지 | 움직임 박스 표시 + 감지 상태 표시 |
| 자동 모션 녹화 | 모션 발생 시 녹화 시작, 지정 시간 무모션 시 종료 |
| 포즈 검출 | MediaPipe Pose 스켈레톤 오버레이 |
| 스냅샷 | 현재 프레임 PNG 저장 |

---

## 클릭 UI 버튼

상단 컨트롤 바 버튼:

`REC`, `FILTER`, `CODEC`, `FPS-`, `FPS+`, `FLIP`, `MOTION`, `POSE`, `AUTO`, `SHOT`

---

## 키보드 조작

| 키 | 동작 |
|:---:|---|
| `Space` | 녹화 시작/종료 |
| `ESC` | 종료 |
| `1` / `2` / `3` | 필터 `normal / gray / edge` |
| `C` | 코덱 순환 변경 |
| `+` / `-` | FPS 증가/감소 |
| `F` | 좌우 반전 ON/OFF |
| `M` | 모션 감지 ON/OFF |
| `P` | 포즈 검출 ON/OFF |
| `A` | 자동 모션 녹화 ON/OFF |
| `S` | 스냅샷 저장 |

---

## 실행 옵션

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--source` | `0` | 카메라 인덱스 또는 스트림 URL |
| `--fps` | `30.0` | 초기 녹화 FPS |
| `--codec` | `mp4v` | 초기 FourCC 코덱 |
| `--output-dir` | `recordings` | 녹화/스냅샷 저장 폴더 |
| `--motion-min-area` | `1200` | 모션 감지 최소 contour 면적 |
| `--motion-hold-seconds` | `2.0` | 자동 모션 녹화 종료 지연 시간 |

---

## 설치 (Python 3.11 권장)

### 1) 가상환경 생성

```powershell
C:\Users\owen0\AppData\Local\Programs\Python\Python311\python.exe -m venv .venv311
```

### 2) 의존성 설치

```powershell
.\.venv311\Scripts\python.exe -m pip install opencv-contrib-python mediapipe==0.10.14
```

### 3) 실행

```powershell
.\.venv311\Scripts\python.exe video_recorder.py
```

### 실행 예시

```powershell
# 기본 웹캠
.\.venv311\Scripts\python.exe video_recorder.py --source 0

# 코덱/FPS 지정
.\.venv311\Scripts\python.exe video_recorder.py --codec XVID --fps 25

# 모션 민감도 지정
.\.venv311\Scripts\python.exe video_recorder.py --motion-min-area 1500 --motion-hold-seconds 3
```

---

## 출력 파일

- 기본 폴더: `recordings/`
- 녹화 파일: `recording_YYYYMMDD_HHMMSS_CODEC.mp4` 또는 `.avi`
- 스냅샷 파일: `snapshot_YYYYMMDD_HHMMSS.png`

---

## 과제 요구사항 체크

- OpenCV `VideoCapture` 사용
- OpenCV `VideoWriter` 사용
- Preview/Record 모드 전환
- Record 모드 표시(빨간 인디케이터)
- `Space` 모드 전환
- `ESC` 종료

---

## 트러블슈팅

- `POSE`가 켜지지 않으면:
  - 반드시 `.venv311`로 실행 중인지 확인
  - 시작 로그에서 Python 경로가 `.venv311\Scripts\python.exe`인지 확인
  - `mediapipe` 버전이 `0.10.14`인지 확인

- VS Code Code Runner 사용 시:
  - 워크스페이스 설정의 Python 실행기가 `.venv311`로 지정되어 있어야 함
