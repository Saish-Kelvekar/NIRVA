
from huggingface_hub import snapshot_download

model_id = "Qwen/Qwen3-0.6B"

model_path = snapshot_download(
    repo_id=model_id,
    local_dir="../models/qwen3-0.6b"
)

print("Qwen3 downloaded successfully!")
print("Location:", model_path)
