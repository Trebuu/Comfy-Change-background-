# Comfy — Change Background

Self-contained ComfyUI provisioning for the **Change background / Character replacement**
workflow (Qwen-Image-Edit 2509 + SeedVR2 upscale), for running on **RunPod**.

This repo is a **provisioning system**, not a model store — the ~52.5 GB of models are
downloaded onto the pod by `provisioning/provision.sh`.

```
workflows/change_background.json     the workflow (load this in ComfyUI)
provisioning/custom_nodes.txt        9 node packs, pinned
provisioning/models.txt              7 model files (all URLs verified)
provisioning/provision.sh            installs nodes + downloads models
```

Target hardware: **80 GB GPU (A100/H100)** — runs the full bf16 edit model.

## What it needs

**Custom nodes (9):** LayerStyle + LayerStyle_Advance (BiRefNet mask), KJNodes,
controlnet_aux (DWPose), essentials, TTP_Toolset (tiling), QwenEditUtils,
SeedVR2_VideoUpscaler, KOOK_ImageCompression.

**Models (~52.5 GB):**
| File | Folder | Size |
|---|---|---|
| qwen_image_edit_2509_bf16.safetensors | diffusion_models | 38.1 GB |
| qwen_2.5_vl_7b_fp8_scaled.safetensors | text_encoders | 8.7 GB |
| Qwen-Image-Edit-2509-Lightning-8steps-V1.0-fp32.safetensors | loras | 1.6 GB |
| RoleScene_Blend.safetensors | loras | 0.3 GB |
| seedvr2_ema_3b_fp8_e4m3fn.safetensors | SEEDVR2 | 3.2 GB |
| ema_vae_fp16.safetensors | SEEDVR2 | 0.5 GB |
| qwen_image_vae.safetensors | vae | 0.2 GB |

**Auto-downloaded on first run** (needs internet, the pod has it): `BiRefNet-General`
(~1 GB), `VITMatte` (~1 GB), and DWPose ONNX models (~0.4 GB). The nodes fetch these
themselves the first time the graph runs.

> Disk: budget **~80 GB minimum**; provision a **100 GB** volume for headroom.

## Deploy on RunPod (normal ComfyUI pod)

1. **Network Volume** (~100 GB) in a region with A100/H100 — mounts at `/workspace`.
2. **Deploy Pod:** A100 80GB / H100, a **ComfyUI template** (pick one that installs
   ComfyUI under `/workspace`), attach the volume.
3. **Provision** in the pod's web terminal:
   ```bash
   cd /workspace
   git clone https://<GITHUB_PAT>@github.com/Trebuu/Comfy-Change-background-.git
   export HF_TOKEN=hf_xxx        # optional, faster
   bash Comfy-Change-background-/provisioning/provision.sh
   ```
   (Repo is private → use a GitHub Personal Access Token, or make it public.)
   First run ~10–20 min. Then **restart ComfyUI** so the new nodes load.
4. **Generate:** open `https://<POD_ID>-8188.proxy.runpod.net`, load
   `workflows/change_background.json`, set your inputs, Run.

## Note
The RoleScene Blend LoRA (Chinese name `角色置景_RoleScene Blend`) is referenced inside
the workflow as `RoleScene_Blend.safetensors` — renamed to plain ASCII to avoid
filename issues on Linux. `provision.sh` downloads it under that exact name, so the
graph loads with no edits.
