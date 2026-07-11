#!/usr/bin/env bash
###############################################################################
# Trebuu/Comfy - RunPod provisioning script
#
# Installs the exact custom-node packs and downloads every model required by
# the workflows in ./workflows, into a persistent ComfyUI install.
#
# Designed for a RunPod ComfyUI pod on a persistent network volume.
# Compatible with the ai-dock/comfyui PROVISIONING_SCRIPT convention, and also
# runnable by hand:  bash provision.sh
#
# Optional environment variables:
#   COMFYUI_DIR    - path to ComfyUI (auto-detected if unset)
#   MODELS_ROOT    - where models go (default: $COMFYUI_DIR/models). Point this at
#                    a network volume, e.g. /workspace/models, to provision a
#                    serverless volume without a full ComfyUI present.
#   HF_TOKEN       - HuggingFace token (for gated/faster downloads)
#   CIVITAI_TOKEN  - Civitai token (for Civitai-hosted LoRAs)
#   SKIP_NODES=1   - skip custom-node install
#   SKIP_MODELS=1  - skip model download
###############################################################################
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODES_LIST="$HERE/custom_nodes.txt"
MODELS_LIST="$HERE/models.txt"

# ---- locate ComfyUI ---------------------------------------------------------
if [[ -z "${COMFYUI_DIR:-}" ]]; then
  for c in /ComfyUI /workspace/ComfyUI /opt/ComfyUI "$HOME/ComfyUI" ./ComfyUI; do
    [[ -f "$c/main.py" ]] && COMFYUI_DIR="$c" && break
  done
fi
# ComfyUI is required for node install; models-only runs (SKIP_NODES=1 + MODELS_ROOT) don't need it.
if [[ -z "${COMFYUI_DIR:-}" || ! -f "${COMFYUI_DIR:-}/main.py" ]]; then
  if [[ "${SKIP_NODES:-0}" == "1" && -n "${MODELS_ROOT:-}" ]]; then
    echo ">> ComfyUI not found — models-only mode into MODELS_ROOT=$MODELS_ROOT"
  else
    echo "ERROR: could not find ComfyUI (set COMFYUI_DIR)." >&2; exit 1
  fi
else
  echo ">> ComfyUI at: $COMFYUI_DIR"
fi
MODELS_ROOT="${MODELS_ROOT:-$COMFYUI_DIR/models}"
echo ">> models root: $MODELS_ROOT"

# pick a python
PY="${PYTHON:-python3}"; command -v "$PY" >/dev/null || PY=python

# safe whitespace trim (pure bash; unlike `xargs` it never chokes on quotes/apostrophes)
trim() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; s="${s%"${s##*[![:space:]]}"}"; printf '%s' "$s"; }

# ensure downloaders
command -v aria2c >/dev/null || { echo ">> installing aria2"; apt-get update -y && apt-get install -y aria2 || true; }
$PY -m pip install -q --upgrade "huggingface_hub[hf_xet]" >/dev/null 2>&1 || $PY -m pip install -q --upgrade huggingface_hub || true

HF_ARGS=(); [[ -n "${HF_TOKEN:-}" ]] && HF_ARGS=(--token "$HF_TOKEN")

# ---- helpers ----------------------------------------------------------------
dl() {  # dl <url> <dest_dir> <filename>
  local url="$1" dir="$2" fn="$3"
  mkdir -p "$dir"
  if [[ -f "$dir/$fn" ]]; then echo "   [skip] $fn (exists)"; return 0; fi
  echo "   [get ] $fn -> $dir"
  if [[ "$url" == *"huggingface.co"* ]]; then
    # repo/path form:  hf:REPO_ID:PATH_IN_REPO
    :
  fi
  local extra=()
  [[ "$url" == *"civitai.com"* && -n "${CIVITAI_TOKEN:-}" ]] && url="${url}?token=${CIVITAI_TOKEN}"
  [[ -n "${HF_TOKEN:-}" && "$url" == *"huggingface.co"* ]] && extra=(--header="Authorization: Bearer ${HF_TOKEN}")
  aria2c -x16 -s16 -k1M --continue=true --console-log-level=warn --summary-interval=0 \
         "${extra[@]}" "$url" -d "$dir" -o "$fn"
}

# ---- 1. custom nodes --------------------------------------------------------
if [[ "${SKIP_NODES:-0}" != "1" && -f "$NODES_LIST" ]]; then
  echo ">> Installing custom nodes..."
  cd "$COMFYUI_DIR/custom_nodes"
  while IFS='|' read -r repo commit || [[ -n "$repo" ]]; do
    repo="$(trim "$repo")"; commit="$(trim "${commit:-}")"
    [[ -z "$repo" || "$repo" == \#* ]] && continue
    name="$(basename "$repo" .git)"
    if [[ -d "$name/.git" ]]; then
      echo "   [have] $name"
    else
      echo "   [clone] $name"
      git clone --recurse-submodules "$repo" "$name" || { echo "   !! clone failed: $repo"; continue; }
    fi
    if [[ -n "$commit" && "$commit" != \#* ]]; then git -C "$name" checkout -q "$commit" 2>/dev/null || echo "   !! pin failed $name@$commit"; fi
    [[ -f "$name/requirements.txt" ]] && $PY -m pip install -q -r "$name/requirements.txt" || true
  done < "$NODES_LIST"
fi

# ---- 2. models --------------------------------------------------------------
if [[ "${SKIP_MODELS:-0}" != "1" && -f "$MODELS_LIST" ]]; then
  echo ">> Downloading models..."
  while IFS='|' read -r url subdir fn || [[ -n "$url" ]]; do
    url="$(trim "$url")"; subdir="$(trim "${subdir:-}")"; fn="$(trim "${fn:-}")"
    [[ -z "$url" || "$url" == \#* ]] && continue
    [[ -z "$fn" ]] && fn="$(basename "${url%%\?*}")"
    dl "$url" "$MODELS_ROOT/$subdir" "$fn"
  done < "$MODELS_LIST"
fi

echo ">> Provisioning complete."
