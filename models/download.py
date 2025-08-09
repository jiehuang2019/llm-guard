from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="protectai/deberta-v3-base-prompt-injection-v2",      # e.g. "Declare-lab/deberta-v3-base-prompt-injection-v2"
    local_dir="./models/deberta-v3-base-prompt-injection-v2",
    local_dir_use_symlinks=False,
    token=None   # uses HF_TOKEN env automatically
)
print("✅ downloaded")

