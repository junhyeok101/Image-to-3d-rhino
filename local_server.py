"""
Local Image-to-3D server (FastAPI) — TripoSR / InstantMesh wrapper.

이 서버는 index.html의 "Local server" 모드에서 호출되는 엔드포인트입니다.
WSL2 + NVIDIA GPU에서 실행하는 것을 가정합니다.

설치 / 실행:
  pip install fastapi uvicorn pillow numpy trimesh
  # + 실제 모델 의존성 (TripoSR / InstantMesh) — LOCAL_SETUP.md 참고
  python local_server.py

  → http://localhost:7860/health 로 헬스체크
  → POST http://localhost:7860/generate 로 이미지 보냄

엔드포인트 사양 (index.html과 호환):
  POST /generate
    Body (JSON): { "image_b64": "<base64>", "image_mime": "image/png", "output_format": "glb" }
    Response (JSON): { "mesh_url": "/files/abc.glb" }
                  또는 { "glb_b64": "<base64 binary>" }
                  또는 직접 binary GLB (Content-Type: model/gltf-binary)

ENV 변수:
  MODEL_KIND=triposr | instantmesh | mock   (default: mock)
  PORT=7860
  DEVICE=cuda | cpu  (default: cuda)
  CKPT_DIR=./checkpoints  (모델 가중치 위치)
"""

import os
import io
import sys
import time
import uuid
import base64
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")
log = logging.getLogger("local-3d")

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse, Response
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("Missing deps. Run: pip install fastapi uvicorn pillow numpy trimesh", file=sys.stderr)
    raise

from PIL import Image

ROOT = Path(__file__).parent.resolve()
OUTPUT_DIR = ROOT / "_local_meshes"
OUTPUT_DIR.mkdir(exist_ok=True)

MODEL_KIND = os.environ.get("MODEL_KIND", "mock").lower()
DEVICE = os.environ.get("DEVICE", "cuda").lower()
CKPT_DIR = os.environ.get("CKPT_DIR", str(ROOT / "checkpoints"))
PORT = int(os.environ.get("PORT", "7860"))

# Lazy model holder
_model_cache = {"obj": None, "kind": None}

# --------------------------------------------------------------------------- #
#  Model loaders                                                              #
# --------------------------------------------------------------------------- #
def load_triposr():
    """
    TripoSR — VAST-AI-Research/TripoSR
    git clone https://github.com/VAST-AI-Research/TripoSR.git
    pip install -r TripoSR/requirements.txt
    """
    log.info("Loading TripoSR...")
    from tsr.system import TSR
    model = TSR.from_pretrained(
        "stabilityai/TripoSR",
        config_name="config.yaml",
        weight_name="model.ckpt",
    )
    model.renderer.set_chunk_size(8192)
    if DEVICE == "cuda":
        import torch
        model.to("cuda")
    log.info("TripoSR ready.")
    return model


def load_instantmesh():
    """InstantMesh는 subprocess 방식으로 호출 (run_instantmesh 함수 참조)."""
    log.info("InstantMesh: subprocess mode — run.py를 매 요청마다 호출합니다.")
    log.info(f"  repo: {os.environ.get('INSTANTMESH_REPO', str(Path.home() / 'InstantMesh'))}")
    return "subprocess"


def get_model():
    if _model_cache["obj"] is None:
        if MODEL_KIND == "triposr":
            _model_cache["obj"] = load_triposr()
        elif MODEL_KIND == "instantmesh":
            _model_cache["obj"] = load_instantmesh()
        elif MODEL_KIND == "mock":
            log.warning("MOCK mode — returning a sample cube. Set MODEL_KIND=triposr or instantmesh for real model.")
            _model_cache["obj"] = "mock"
        else:
            raise RuntimeError(f"Unknown MODEL_KIND: {MODEL_KIND}")
        _model_cache["kind"] = MODEL_KIND
    return _model_cache["obj"]


# --------------------------------------------------------------------------- #
#  Inference                                                                   #
# --------------------------------------------------------------------------- #
def run_triposr(model, pil_img: Image.Image, out_path: Path):
    import torch
    # Background removal + resize (TripoSR provides utilities)
    try:
        from tsr.utils import remove_background, resize_foreground
        import rembg
        session = rembg.new_session()
        img = remove_background(pil_img.convert("RGBA"), session)
        img = resize_foreground(img, 0.85)
    except Exception as e:
        log.warning(f"rembg failed ({e}), using raw image")
        img = pil_img.convert("RGB")

    with torch.no_grad():
        scene_codes = model([img], device=DEVICE if DEVICE == "cuda" else "cpu")
        meshes = model.extract_mesh(scene_codes, has_vertex_color=True, resolution=256)
    mesh = meshes[0]
    mesh.export(str(out_path))
    return out_path


def run_instantmesh(_unused, pil_img: Image.Image, out_path: Path) -> Path:
    """
    InstantMesh의 run.py 를 subprocess로 호출.
    이 서버는 InstantMesh의 conda env (instantmesh) 안에서 실행되어야 합니다.

      conda activate instantmesh
      python local_server.py

    환경변수:
      INSTANTMESH_REPO   (default: ~/InstantMesh)
      INSTANTMESH_CONFIG (default: instant-mesh-large)
    """
    import subprocess, shutil

    repo = Path(os.environ.get("INSTANTMESH_REPO", str(Path.home() / "InstantMesh")))
    config_name = os.environ.get("INSTANTMESH_CONFIG", "instant-mesh-large")
    config_rel = f"configs/{config_name}.yaml"

    if not (repo / "run.py").exists():
        raise RuntimeError(f"InstantMesh repo not found: {repo}/run.py")

    # 1) Save input image to InstantMesh repo
    in_dir = repo / "_local_inputs"
    in_dir.mkdir(exist_ok=True)
    stem = f"in_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    in_path = in_dir / f"{stem}.png"
    pil_img.convert("RGBA").save(in_path)
    log.info(f"InstantMesh input saved: {in_path}")

    # 2) Run inference (no --export_texmap to keep it faster; geometry only)
    in_path_rel = in_path.relative_to(repo)
    cmd = ["python", "run.py", config_rel, str(in_path_rel)]
    log.info(f"  exec: {' '.join(cmd)}  (cwd={repo})")

    t0 = time.time()
    proc = subprocess.run(
        cmd, cwd=str(repo),
        capture_output=True, text=True,
        timeout=int(os.environ.get("INSTANTMESH_TIMEOUT", "900")),
    )
    elapsed = time.time() - t0
    if proc.returncode != 0:
        log.error(f"stdout tail:\n{proc.stdout[-800:]}")
        log.error(f"stderr tail:\n{proc.stderr[-1500:]}")
        raise RuntimeError(f"InstantMesh CLI rc={proc.returncode}: {proc.stderr[-300:]}")
    log.info(f"InstantMesh inference done in {elapsed:.1f}s")

    # 3) Find output mesh — InstantMesh saves to outputs/<config>/meshes/<stem>.obj
    meshes_dir = repo / "outputs" / config_name / "meshes"
    obj_path = meshes_dir / f"{stem}.obj"
    if not obj_path.exists():
        cands = sorted(meshes_dir.glob(f"{stem}*.obj"))
        if not cands:
            # fallback to most recent
            cands = sorted(meshes_dir.glob("*.obj"), key=lambda p: p.stat().st_mtime, reverse=True)
            if cands:
                log.warning(f"이름 매칭 OBJ 없음, 가장 최근 OBJ 사용: {cands[0].name}")
        if not cands:
            raise RuntimeError(f"No output OBJ in {meshes_dir}")
        obj_path = cands[0]
    log.info(f"InstantMesh output OBJ: {obj_path} ({obj_path.stat().st_size//1024} KB)")

    # 4) OBJ+MTL+PNG를 OUTPUT_DIR에 복사 — trimesh 변환 없이 그대로 서빙
    import re as _re
    stem_out = out_path.stem
    obj_out  = OUTPUT_DIR / f"{stem_out}.obj"
    mtl_out  = OUTPUT_DIR / f"{stem_out}.mtl"
    tex_out  = OUTPUT_DIR / f"{stem_out}.png"

    shutil.copy2(obj_path, obj_out)
    log.info(f"OBJ copied: {obj_out.name} ({obj_out.stat().st_size//1024} KB)")

    mtl_src = obj_path.with_suffix('.mtl')
    has_mtl = mtl_src.exists()
    if has_mtl:
        mtl_text = mtl_src.read_text(errors='replace')
        mtl_text = _re.sub(r'map_Kd\s+\S+', f'map_Kd {stem_out}.png', mtl_text)
        mtl_out.write_text(mtl_text)
        log.info(f"MTL written: {mtl_out.name}")

    tex_src = obj_path.with_suffix('.png')
    if not tex_src.exists():
        pngs = sorted(obj_path.parent.glob('*.png'), key=lambda p: p.stat().st_size, reverse=True)
        if pngs:
            tex_src = pngs[0]
    has_tex = tex_src.exists()
    if has_tex:
        shutil.copy2(tex_src, tex_out)
        log.info(f"Texture copied: {tex_out.name} ({tex_out.stat().st_size//1024} KB)")
    else:
        log.warning("텍스처 PNG를 찾지 못했습니다.")
        tex_out = None

    return {"obj": obj_out, "mtl": mtl_out if has_mtl else None, "tex": tex_out}


def run_mock(pil_img: Image.Image, out_path: Path):
    """샘플 큐브를 GLB로 출력 — 서버/사이트 연결 테스트용."""
    import trimesh
    import numpy as np
    box = trimesh.creation.box(extents=(1.0, 1.0, 1.0))
    # 색상 입히기 (디버그용)
    box.visual.vertex_colors = np.tile([88, 166, 255, 255], (len(box.vertices), 1))
    box.export(str(out_path))
    return out_path


def generate_mesh(pil_img: Image.Image):
    """Returns Path (mock/triposr) or dict {obj, mtl, tex} (instantmesh)."""
    model = get_model()
    stem = f"mesh_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    out_path = OUTPUT_DIR / (stem + ".glb")

    t0 = time.time()
    if MODEL_KIND == "triposr":
        result = run_triposr(model, pil_img, out_path)
    elif MODEL_KIND == "instantmesh":
        result = run_instantmesh(model, pil_img, out_path)
    else:
        result = run_mock(pil_img, out_path)
    log.info(f"Generated in {time.time()-t0:.1f}s")
    return result


# --------------------------------------------------------------------------- #
#  FastAPI app                                                                #
# --------------------------------------------------------------------------- #
app = FastAPI(title="Local Image-to-3D")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)

# Static mount for serving generated GLB files
app.mount("/files", StaticFiles(directory=str(OUTPUT_DIR)), name="files")


class GenerateBody(BaseModel):
    image_b64: str
    image_mime: str | None = "image/png"
    output_format: str | None = "glb"


@app.get("/")
def root():
    return {
        "service": "Local Image-to-3D",
        "model_kind": MODEL_KIND,
        "device": DEVICE,
        "endpoints": ["GET /health", "POST /generate"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "model_kind": MODEL_KIND, "device": DEVICE, "model_loaded": _model_cache["obj"] is not None}


@app.post("/generate")
def generate(body: GenerateBody):
    try:
        b64 = body.image_b64.split(",")[-1]
        img_bytes = base64.b64decode(b64)
        pil_img = Image.open(io.BytesIO(img_bytes))
    except Exception as e:
        raise HTTPException(400, f"Invalid image_b64: {e}")

    try:
        result = generate_mesh(pil_img)
    except NotImplementedError as e:
        raise HTTPException(501, str(e))
    except Exception as e:
        log.exception("Inference failed")
        raise HTTPException(500, f"Inference failed: {e}")

    # Build response — instantmesh returns dict {obj, mtl, tex}; others return a Path
    if isinstance(result, dict):
        resp = {"model_kind": MODEL_KIND}
        if result.get("obj"):
            resp["obj_url"] = f"/files/{result['obj'].name}"
            resp["size_bytes"] = result["obj"].stat().st_size
        if result.get("mtl"):
            resp["mtl_url"] = f"/files/{result['mtl'].name}"
        if result.get("tex"):
            resp["tex_url"] = f"/files/{result['tex'].name}"
        return JSONResponse(resp)
    else:
        public_url = f"/files/{result.name}"
        return JSONResponse({"mesh_url": public_url, "size_bytes": result.stat().st_size, "model_kind": MODEL_KIND})


# --------------------------------------------------------------------------- #
#  Entrypoint                                                                 #
# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    log.info(f"Starting server on :{PORT}  (MODEL_KIND={MODEL_KIND}, DEVICE={DEVICE})")
    if MODEL_KIND == "mock":
        log.warning("== MOCK 모드입니다 (큐브 반환). MODEL_KIND=triposr 또는 instantmesh 로 실행하세요. ==")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")