
import json
import time
import gc
from pathlib import Path

import torch
from transformers import AutoTokenizer, AutoModelForCausalLM


PROJECT_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = PROJECT_DIR / "data" / "nirva_eval.json"
RESULTS_DIR = Path(__file__).parent / "results"

MODELS = {
    "qwen2.5-0.5b": PROJECT_DIR / "models" / "qwen2.5-0.5b-instruct",
    "qwen3-0.6b": PROJECT_DIR / "models" / "qwen3-0.6b",
}

MAX_NEW_TOKENS = 150

SYSTEM_PROMPT = """
You are an assistant being evaluated for NIRVA, an assistant
focused on Dandeli, Karnataka, India.

Answer the user's question clearly.
Do not invent facts, locations, businesses, fees or phone numbers.
If you do not know something, acknowledge the uncertainty.
For unrelated questions, answer normally for this baseline test.
"""


def evaluate_model(model_name, model_path, questions):
    print(f"\n{'=' * 55}")
    print(f"Evaluating: {model_name}")
    print(f"{'=' * 55}")

    tokenizer = AutoTokenizer.from_pretrained(str(model_path))

    model = AutoModelForCausalLM.from_pretrained(
        str(model_path),
        dtype=torch.float32
    )
    model.eval()

    results = []

    for item in questions:
        question = item["question"]

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question}
        ]

        prompt = tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
            enable_thinking=False if "qwen3" in model_name else None
        )

        inputs = tokenizer(prompt, return_tensors="pt")

        start = time.perf_counter()

        with torch.inference_mode():
            outputs = model.generate(
                **inputs,
                max_new_tokens=MAX_NEW_TOKENS,
                do_sample=False
            )

        generation_time = time.perf_counter() - start

        new_tokens = outputs[0][inputs["input_ids"].shape[1]:]
        response = tokenizer.decode(
            new_tokens,
            skip_special_tokens=True
        )

        token_count = len(new_tokens)
        tokens_per_second = (
            token_count / generation_time
            if generation_time > 0 else 0
        )

        result = {
            "id": item["id"],
            "category": item["category"],
            "question": question,
            "response": response,
            "generated_tokens": token_count,
            "generation_time_seconds": round(generation_time, 2),
            "tokens_per_second": round(tokens_per_second, 2)
        }

        results.append(result)

        print(f"\nQuestion {item['id']} ({item['category']})")
        print("Question:", question)
        print("Response:", response)
        print("Time:", result["generation_time_seconds"], "seconds")
        print("Tokens/sec:", result["tokens_per_second"])

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    output_file = RESULTS_DIR / f"{model_name}.json"

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(results, file, indent=4, ensure_ascii=False)

    print(f"\nSaved results to: {output_file}")

    del model
    del tokenizer
    gc.collect()


def main():
    with open(DATASET_PATH, "r", encoding="utf-8") as file:
        questions = json.load(file)

    for model_name, model_path in MODELS.items():
        if not model_path.exists():
            print(f"\nSkipping {model_name}: model not found.")
            continue

        evaluate_model(model_name, model_path, questions)


if __name__ == "__main__":
    main()
