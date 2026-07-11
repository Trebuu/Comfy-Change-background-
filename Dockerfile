# RunPod Serverless worker for the Change-background workflow.
# Reproduces the exact working pod environment. Models are NOT baked — they live on
# the network volume (mounted at /runpod-volume; see serverless/start.sh).
#
# Bakes every fix discovered while validating on the pod:
#   - PyTorch cu128 (Blackwell sm_120 support — base torch 2.4 can't run this GPU)
#   - all 9 custom-node packs incl. RES4LYF (beta57 scheduler)
#   - opencv-contrib-python-headless (LayerStyle guidedFilter)
#   - BiRefNet loaded as fp32 (dtype-mismatch patch)
FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

ENV DEBIAN_FRONTEND=noninteractive PIP_PREFER_BINARY=1 PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      git aria2 ffmpeg libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

# 1) Blackwell-capable PyTorch (matches validated pod: torch 2.11+cu128)
RUN pip install --upgrade --no-cache-dir torch torchvision torchaudio \
      --index-url https://download.pytorch.org/whl/cu128

# 2) ComfyUI
RUN git clone https://github.com/comfyanonymous/ComfyUI.git /ComfyUI && \
    pip install --no-cache-dir -r /ComfyUI/requirements.txt

# 3) custom nodes + their python deps (custom_nodes.txt includes RES4LYF)
COPY provisioning /provisioning
RUN SKIP_MODELS=1 COMFYUI_DIR=/ComfyUI bash /provisioning/provision.sh

# 4) opencv guidedFilter fix (LayerStyle)
RUN pip uninstall -y opencv-python opencv-python-headless opencv-contrib-python opencv-contrib-python-headless 2>/dev/null || true && \
    pip install --no-cache-dir opencv-contrib-python-headless

# 5) BiRefNet dtype fix (load model in fp32 to match fp32 input)
RUN sed -i 's#from_pretrained(model_path, trust_remote_code=True)#from_pretrained(model_path, trust_remote_code=True).float()#' \
      /ComfyUI/custom_nodes/ComfyUI_LayerStyle_Advance/py/birefnet_ultra_v2.py

# 6) worker
RUN pip install --no-cache-dir runpod
COPY serverless/handler.py /handler.py
COPY serverless/start.sh /start.sh
RUN chmod +x /start.sh

CMD ["/start.sh"]
