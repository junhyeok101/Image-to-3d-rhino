# 로컬 Image-to-3D 서버 셋업 (WSL2)

`fal.ai` 대신 본인 PC의 GPU로 TripoSR / InstantMesh를 돌리는 방법.
사이트(`index.html`)는 `http://localhost:7860/generate` 같은 로컬 엔드포인트만 호출하면 됩니다.

---

## 0. 사전 요구사항

- Windows 11 + WSL2 (Ubuntu 22.04 권장)
- NVIDIA GPU (TripoSR: 6GB VRAM 이상, InstantMesh: 12GB 이상)
- WSL2에 NVIDIA 드라이버 패스스루 활성화
  - Windows 측에 최신 NVIDIA 드라이버만 설치하면 자동 노출됨
  - WSL 안에서 `nvidia-smi` 가 작동하면 OK

```bash
nvidia-smi   # GPU 보이면 통과
```

---

## 1. 빠른 시작 (MOCK 모드 — 연결 테스트만)

먼저 사이트와 서버 연결이 잘 되는지 확인하기 위해 가짜(큐브 반환) 모드로 띄워봅니다.

```bash
cd /mnt/c/Users/<your>/Desktop/final_project    # 또는 사이트 폴더
python3 -m venv venv
source venv/bin/activate
pip install fastapi uvicorn pillow trimesh numpy
MODEL_KIND=mock python local_server.py
```

브라우저:
- `index.html` 열기 → "Image → 3D 모델" 에서 **🖥 Local server** 선택
- URL: `http://localhost:7860/generate`
- 테스트 누르면 "로컬 서버 OK" 표시
- 아무 이미지 업로드 후 실행 → 큐브 GLB 받아져서 .3dm 다운로드까지 확인

이게 되면 사이트와 서버 통신은 정상.

---

## 2. TripoSR (추천 — 가벼움, ~10초 추론)

```bash
# 가상환경 활성 상태에서
git clone https://github.com/VAST-AI-Research/TripoSR.git
cd TripoSR
pip install -r requirements.txt
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
pip install rembg
cd ..

# local_server.py는 TripoSR repo와 같은 venv를 공유해야 합니다.
# tsr 모듈을 import 가능하게 하려면:
#   1) TripoSR 폴더에서 실행하거나
#   2) PYTHONPATH=./TripoSR python local_server.py 처럼 지정

MODEL_KIND=triposr DEVICE=cuda PYTHONPATH=./TripoSR python local_server.py
```

첫 실행 시 HuggingFace에서 `stabilityai/TripoSR` 체크포인트를 자동 다운로드 (~1.5GB).

---

## 3. InstantMesh (더 고품질, ~30~60초 추론, 12GB+ VRAM)

```bash
git clone https://github.com/TencentARC/InstantMesh.git
cd InstantMesh
pip install -r requirements.txt
# 체크포인트 다운로드:
mkdir -p ckpts
wget https://huggingface.co/TencentARC/InstantMesh/resolve/main/instant_mesh_large.ckpt -O ckpts/instant_mesh_large.ckpt
cd ..

INSTANTMESH_REPO=./InstantMesh CKPT_DIR=./InstantMesh/ckpts \
  MODEL_KIND=instantmesh DEVICE=cuda \
  python local_server.py
```

⚠️ `local_server.py`의 `run_instantmesh` 함수는 InstantMesh repo의 `run.py` 로직을 추가로 구현해야 동작합니다 (multi-view 생성 → mesh 추출). InstantMesh repo의 `app.py` 가 가장 깔끔한 참고자료입니다.

---

## 4. 한 번에 띄우는 셸 alias (편의용)

```bash
# ~/.bashrc에 추가
alias mesh-server="cd /mnt/c/Users/<you>/Desktop/final_project && \
  source venv/bin/activate && \
  MODEL_KIND=triposr DEVICE=cuda PYTHONPATH=./TripoSR \
  python local_server.py"
```

이후 WSL 터미널에서 `mesh-server` 한 마디로 켜집니다.

---

## 5. 윈도우↔WSL 포트 문제

WSL2의 `localhost:7860`은 Windows의 `localhost:7860`으로 자동 포워딩됩니다 (WSL2 기본 동작). 안되면:

```powershell
# PowerShell (관리자) — 포트 미러링
netsh interface portproxy add v4tov4 listenport=7860 connectport=7860 connectaddress=$(wsl hostname -I)
```

또는 WSL 2 `~/.wslconfig`에 `networkingMode=mirrored` 설정.

---

## 6. 사이트에서 사용

1. WSL에서 서버 실행 (`python local_server.py`)
2. Windows에서 `index.html` 더블클릭 (혹은 `python serve.py`)
3. UI에서:
   - "Image → 3D 모델" → **🖥 Local server (WSL/로컬 GPU)** 선택
   - URL: `http://localhost:7860/generate` (기본값 그대로)
   - "테스트" → 로컬 서버 OK
4. 이미지 업로드 → 실행 → .3dm 다운로드

---

## 7. 트러블슈팅

| 증상 | 해결 |
|------|------|
| `CORS error` | `local_server.py`는 이미 `allow_origins=["*"]` 설정. 브라우저 재시작 시도. |
| `nvidia-smi` 인식 안 됨 | WSL용 NVIDIA 드라이버를 윈도우에 다시 설치. |
| OOM (Out of memory) | TripoSR로 전환하거나 `model.renderer.set_chunk_size(4096)` 으로 낮춤. |
| 모델 로딩이 매우 느림 | HF 캐시(`~/.cache/huggingface`) 가 매번 새로 받히는지 확인. |
| `mesh_url`이 상대경로로 옴 | 정상 — 사이트가 자동으로 base URL 붙임. |
| 다른 포트 쓰고 싶음 | `PORT=8080 python local_server.py` |

---

## 8. 대안

- **ComfyUI**: ComfyUI에 InstantMesh 노드를 설치하고 ComfyUI의 `/api/prompt` 엔드포인트를 쓰는 방식. 그래프 기반이라 후처리 추가가 쉬움.
- **gradio_client**: 이미 돌고 있는 HF Space나 로컬 Gradio 앱을 `gradio_client`로 호출하는 wrapper로 바꿔도 됨.
- **Triton Server**: 프로덕션 수준 배포라면 NVIDIA Triton Inference Server.

각 옵션도 `POST → GLB URL` 인터페이스만 맞춰주면 사이트는 그대로 동작합니다.
