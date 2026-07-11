#!/usr/bin/env bash
# Serverless entrypoint: point ComfyUI at the volume's models, launch ComfyUI + handler.
set -e
VOL="${RUNPOD_VOLUME:-/runpod-volume}"

# The network volume was populated on a pod where ComfyUI lived at /workspace/ComfyUI,
# so its models are at $VOL/ComfyUI/models. Fall back to $VOL/models if reorganized.
if   [ -d "$VOL/ComfyUI/models" ]; then MODELS="$VOL/ComfyUI/models"
elif [ -d "$VOL/models" ];         then MODELS="$VOL/models"
fi
if [ -n "${MODELS:-}" ]; then
  echo ">> Linking /ComfyUI/models -> $MODELS"
  rm -rf /ComfyUI/models && ln -s "$MODELS" /ComfyUI/models
else
  echo ">> WARNING: no models dir found on $VOL"
fi

# Persist runtime auto-downloads (VITMatte, DWPose) on the volume across cold starts.
export HF_HOME="${HF_HOME:-$VOL/hf_cache}"

echo ">> Starting ComfyUI..."
python -u /ComfyUI/main.py --listen 127.0.0.1 --port 8188 --disable-auto-launch &

echo ">> Starting RunPod handler..."
exec python -u /handler.py
