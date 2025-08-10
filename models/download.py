from huggingface_hub import snapshot_download
import sys
snapshot_download(
    repo_id=f"{sys.argv[1]}/{sys.argv[2]}",      
    local_dir=f"./models/{sys.argv[2]}",
    local_dir_use_symlinks=False,
    token=None   # uses HF_TOKEN env automatically
)
print("✅ downloaded")

