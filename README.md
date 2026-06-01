# Image → Rhino 3D Pipeline

> 한 장의 이미지로 시작하는 완전한 3D 워크플로우  
> **AI 기반 3D 생성** → **텍스처 베이크** → **Rhino `.3dm` 변환** → **갤러리 저장**

**AI & Interior Architecture Design** (HID3132.01-00) — Final Project  
**Live Demo**: [image-to-3d-rhino.vercel.app](https://image-to-3d-rhino.vercel.app)

---

## 개요

사진 한 장을 입력하면 Rhino에서 바로 열 수 있는 `.3dm` 파일을 자동으로 생성합니다.  
InstantMesh AI 모델을 로컬 GPU로 구동하고, ngrok으로 외부에 노출해 Vercel 프론트엔드와 연결합니다.

---

## 파이프라인

```
이미지 입력 (jpg/png)
    │
    ├─ (A) Vision LLM 분석
    │       카테고리 추정 · 실제 치수(mm) 예측
    │
    ├─ (B) InstantMesh (로컬 GPU)
    │       멀티뷰 생성 → 3D Mesh 재구성 → OBJ + 텍스처 PNG 출력
    │
    └─ (C) Mesh → Rhino
            텍스처 → Vertex Color 베이크
            스케일링 (LLM 추정 mm 기준)
            rhino3dm → .3dm 파일 생성
            Supabase 갤러리 저장
```

---

## 기술 스택

| 영역 | 기술 |
|------|------|
| 프론트엔드 | HTML / Vanilla JS / Three.js / rhino3dm.js |
| 3D AI 모델 | InstantMesh (로컬 GPU, WSL2) |
| Vision LLM | Claude / GPT-4o / Gemini (선택) |
| 백엔드 서버 | FastAPI + Uvicorn (Python) |
| 터널링 | ngrok |
| 배포 | Vercel |
| 데이터베이스 | Supabase (PostgreSQL + Storage) |
| 실행 환경 | Python 3.10 / WSL2 / NVIDIA GPU |

---

## 폴더 구조

```
Image-to-3d-rhino/
├── index.html          ← 메인 UI (파이프라인 + 갤러리)
├── local_server.py     ← FastAPI 서버 (InstantMesh 래퍼)
├── serve.py            ← 로컬 개발용 HTTP 서버
├── LOCAL_SETUP.md      ← 로컬 GPU 서버 세팅 가이드
└── README.md
```

---

## 로컬 실행

### 1. InstantMesh 서버 시작 (WSL2)

```bash
conda activate instantmesh
cd /path/to/project

SUPABASE_URL=https://xxxx.supabase.co \
SUPABASE_KEY=your_anon_key \
MODEL_KIND=instantmesh DEVICE=cuda \
python local_server.py
```

### 2. ngrok 터널 오픈

```bash
ngrok http 7860
# → https://xxxx.ngrok-free.dev 형태의 URL 발급
```

### 3. 사이트에서 연결

[image-to-3d-rhino.vercel.app](https://image-to-3d-rhino.vercel.app) 접속 후  
**Image → 3D 모델** 섹션에서 ngrok URL 입력 → 테스트 → 이미지 업로드 → 실행

---

## 갤러리

생성된 3D 모델은 Supabase에 자동 저장되어 갤러리 탭에서 확인할 수 있습니다.

- 입력 이미지 썸네일
- 3D 뷰어 (클릭 시 Three.js 모달)
- LLM 분석 카테고리 · 바운딩 박스(mm) · 스케일
- ❤️ 좋아요
- OBJ / 텍스처 다운로드

---

## 환경변수

| 변수 | 설명 |
|------|------|
| `MODEL_KIND` | `instantmesh` / `triposr` / `mock` |
| `DEVICE` | `cuda` / `cpu` |
| `SUPABASE_URL` | Supabase 프로젝트 URL |
| `SUPABASE_KEY` | Supabase anon 키 |
| `PORT` | 서버 포트 (기본 `7860`) |

---

## TODO

- [ ] 더 복잡한 객체 (신발, 의자) 테스트
- [ ] 갤러리 필터 / 검색
- [ ] .3dm 다운로드 갤러리 연동
- [ ] 모바일 UI 최적화