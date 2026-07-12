# Change-background → Serverless — Session Handoff (2026-07-12)

## Goal
Run the **Change-background / Character-replacement** ComfyUI workflow (Qwen-Image-Edit 2509
+ BiRefNet mask + RoleScene LoRA + SeedVR2 upscale) as a cheap **serverless API** with a simple dashboard.

## Where we stopped (current state)
- ✅ Fully working ComfyUI stack built & validated — **real images generated** on a Vast persistent instance.
- ✅ Captured as a portable **Docker image** (this is the serverless foundation):
  `trebuu/comfy-changebg:instance_44551712_at_July_11th_2026_at_11-09-22_PM_UTC`
  — **63.9 GB, PUBLIC** on Docker Hub. Contains ComfyUI + all 10 node packs + 53 GB models + every fix + the pyworker.
- ✅ Vast persistent instance **destroyed** (no billing). The image is the complete backup.
- ⛔ **BLOCKED:** Vast requires a **$5.00 minimum credit balance** to *create* a serverless endpoint.
  Vast balance is ~**$0.92** → need to top up to **≥ $5** (the test run itself is only ~$0.05–0.10).

## ▶ NEXT STEP (tomorrow) — resume here
1. **Top up the Vast balance to ≥ $5** (recommend $5–10 for headroom).
2. Re-provide credentials (the session scratchpad is wiped each session):
   - Vast API key, R2 keys, HF token. (Docker image is public → no pull auth needed.)
3. Create the serverless endpoint + workergroup from the image (commands below).
4. Trigger the worker → run a Change-background generation → confirm output in the R2 `spoofer` bucket.
5. Wire `ui/app.py` (dashboard) to the serverless endpoint.

### Staged serverless commands (ready to run once balance ≥ $5)
```bash
IMG="trebuu/comfy-changebg:instance_44551712_at_July_11th_2026_at_11-09-22_PM_UTC"
vastai create endpoint --endpoint_name comfy-cbg-sl --cold_workers 0 --min_load 0 --max_workers 1 --inactivity_timeout 180
vastai create workergroup --endpoint_name comfy-cbg-sl \
  --template_hash 9840c43bddc652b5d865085ca3db17b0 \
  --search_params "gpu_ram>=40 disk_space>=140 inet_down>=3000 verified=true rentable=true" \
  --test_workers 1 \
  --launch_args "--image $IMG --disk 120 --env '-e PROVISIONING_SCRIPT= -e S3_ENDPOINT_URL=<r2-endpoint> -e S3_BUCKET_NAME=spoofer -e S3_ACCESS_KEY_ID=<key> -e S3_SECRET_ACCESS_KEY=<secret> -e S3_REGION=auto'"
```
Cheapest suitable host seen: **Q RTX 8000 45 GB, ~$0.24/hr, 7,557 Mbps** (fast pull of the 64 GB image).
Serverless workers need no provisioning (image is baked) → cold-start = pull + ComfyUI start (~3–5 min), under the 13-min timeout.

## Key resources
| Thing | Value |
|---|---|
| GitHub repo (public) | `Trebuu/Comfy-Change-background-` — provisioning, workflow (UI + API format), dashboard `ui/app.py`, Dockerfile |
| Serverless image (public) | `trebuu/comfy-changebg:instance_44551712_at_July_11th_2026_at_11-09-22_PM_UTC` (63.9 GB) |
| R2 output bucket | `spoofer` (Cloudflare R2; endpoint = `https://52678234843ddaf29c1dc2ab279c945f.r2.cloudflarestorage.com`) |
| Vast account | `trebu` |
| Dashboard | `ui/app.py` — generic RunComfy dashboard (auto-detects inputs). Needs adapting to the Vast serverless `/route/`+`/generate/sync` flow. |

### RunComfy deployments (alternative path — abandoned)
- `41cbfd2f` Change-background — **broken**: missing BiRefNet-General model; **can't fix via RunComfy API** (no model/node access). This is why we moved to Vast.
- `f9c1e1f5` One-click Pose Generator — works (single image + pose count).
- `cb8616c0` "Storyboard" — misconfigured: contains the **default SD1.5 example**, not the Storyboard workflow.

## Compatibility fixes discovered (all baked into the image + `provisioning/provision.sh`)
1. **RES4LYF** node — provides the `beta57` scheduler the KSampler uses (else "value not available").
2. **BiRefNet-General** must be pre-placed at `models/BiRefNet/BiRefNet-General/` (node does NOT auto-download for that version) → `snapshot_download("ZhengPeng7/BiRefNet")`.
3. **BiRefNet fp32 patch** — model loads fp16, input is fp32 → `sed …from_pretrained(...).float()` in `ComfyUI_LayerStyle_Advance/py/birefnet_ultra_v2.py`.
4. **opencv guidedFilter** — install `opencv-contrib-python-headless`.
5. **RoleScene Blend LoRA** (角色置景) — from HF `Perfs/blendrole`, saved as `RoleScene_Blend.safetensors` (workflow ref de-CJK'd).
6. **vastai/comfy image quirk A:** node deps must install into ComfyUI's venv `/venv/main/bin/pip`, NOT system python.
7. **vastai/comfy image quirk B:** its `xformers` needs a flash-attn build it lacks → `pip uninstall xformers` (ComfyUI runs `--disable-xformers`; SeedVR2 uses `sdpa`).
8. **Blackwell GPUs (sm_120)** need torch cu128 (only hit on RunPod's RTX 6000; not needed on Ada/Ampere).

## Why serverless was hard (the core lesson)
Serverless demands fast cold-starts, but this workflow needs ~20 min of provisioning (53 GB models + node
builds) — they conflict. **Every platform hit this** (RunPod EU-RO-1 scarcity, RunComfy can't-fix-env, Vast 13-min
timeout). **Fix = pre-baked image** (done, above). The 63.9 GB image is slow to pull on a *new* host but cached
per-host afterward.

## Platform notes
- **Vast** — cheapest + full control + serverless. Chosen. Gotchas: **$5 min balance** to create endpoints; 13-min
  worker load timeout; `vastai take snapshot` commits+pushes the running container to a registry (took ~72 min for 64 GB).
- **RunComfy** — easy but no API to fix the environment → dead end for custom workflows.
- **RunPod** — pods worked (rendered a real image); serverless built but EU-RO-1 lacked 80 GB GPUs.

## ⚠️ Security — ROTATE these (all appeared in the session transcript)
- Vast API key · HuggingFace token · Cloudflare R2 access key/secret · Docker Hub PAT · (RunPod key — resources already deleted)

## Cost snapshot
- Serverless test run: ~$0.05–0.10 on a cheap 45 GB host — but **$5 min balance required to create the endpoint**.
- (Persistent instance was ~$0.24–0.6/hr GPU; stopped-storage on the last host was pricey at $0.33/GB/mo = ~$40/mo for 120 GB — destroyed to avoid it.)
