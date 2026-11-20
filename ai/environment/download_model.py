
from huggingface_hub import snapshot_download

model_id = "Qwen/Qwen2.5-0.5B-Instruct"

model_path = snapshot_download(
    repo_id=model_id,
    local_dir="../models/qwen2.5-0.5b-instruct"
)

print("Model downloaded successfully!")
print("Location:", model_path)
