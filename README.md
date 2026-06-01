# Image → Rhino Object Pipeline

## 프로젝트 개요
이미지(사진)를 입력받아 Rhino 3D 객체(.3dm)로 자동 변환하는 파이프라인

## 목표
- Input: 곡선 형태의 제품 사진 (예: 크록스)
- Output: Rhino에서 바로 열 수 있는 `.3dm` 커브 파일

---

## 파이프라인 흐름

```
[input/]          사용자 제공 이미지 (jpg/png)
    ↓
OpenCV            배경 제거 → 엣지 검출 → 윤곽선 추출
    ↓
[processed/]      중간 결과 저장
                  - _gray.png     흑백 변환
                  - _edge.png     엣지 검출 결과
                  - _contour.png  윤곽선 시각화
    ↓
rhino3dm          윤곽선 좌표 → NURBS 커브 생성
    ↓
[output/]         최종 .3dm 파일 (Rhino에서 바로 열기)
```

---

## 폴더 구조

```
C:\final_project\
  input/       ← 원본 이미지 넣는 곳
  processed/   ← 중간 처리 결과 (엣지, 윤곽선)
  output/      ← Rhino .3dm 파일 출력
  README.md    ← 이 파일
  pipeline.py  ← 실행 스크립트
```

---

## 실행 방법

```bash
python pipeline.py input/crocs.jpg
```

---

## 기술 스택

| 단계 | 도구 |
|------|------|
| 이미지 처리 | OpenCV (cv2) |
| 윤곽선 추출 | Canny Edge + findContours |
| Rhino 파일 생성 | rhino3dm 8.x |
| 실행 환경 | Python 3.12 / WSL2 |

---

## TODO
- [ ] 크록스 이미지 테스트
- [ ] 다중 객체 분리 처리
- [ ] 3D extrude 옵션 추가
