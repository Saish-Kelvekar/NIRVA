
import json
from pathlib import Path
from collections import Counter

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATASET_PATH = PROJECT_DIR / "data" / "train.jsonl"

examples = []
errors = []
questions = []

with open(DATASET_PATH, "r", encoding="utf-8") as file:
    for line_number, line in enumerate(file, start=1):
        if not line.strip():
            continue

        try:
            example = json.loads(line)
        except json.JSONDecodeError as error:
            errors.append(f"Line {line_number}: Invalid JSON - {error}")
            continue

        examples.append(example)

        if "messages" not in example:
            errors.append(f"Line {line_number}: Missing messages")
            continue

        messages = example["messages"]

        if not isinstance(messages, list):
            errors.append(f"Line {line_number}: Messages must be a list")
            continue

        roles = [message.get("role") for message in messages]

        if roles != ["system", "user", "assistant"]:
            errors.append(
                f"Line {line_number}: Expected system, user, assistant roles"
            )
            continue

        for message in messages:
            if not message.get("content", "").strip():
                errors.append(
                    f"Line {line_number}: Empty message content"
                )

        question = messages[1]["content"].strip().lower()
        questions.append((question, line_number))

        if not example.get("source_fact_id"):
            errors.append(
                f"Line {line_number}: Missing source_fact_id"
            )

# Check duplicate questions
question_counts = Counter(question for question, _ in questions)

for question, count in question_counts.items():
    if count > 1:
        errors.append(f"Duplicate question: {question}")

print("\nNIRVA DATASET VALIDATION")
print("-" * 35)
print("Total examples:", len(examples))
print("Unique questions:", len(question_counts))

if errors:
    print("\nValidation errors:")
    for error in errors:
        print("-", error)
else:
    print("\nAll structural checks passed!")

# Show category distribution using source IDs
categories = Counter(
    "behaviour" if example.get("source_fact_id", "").startswith("BEHAVIOUR")
    else "knowledge"
    for example in examples
)

print("\nExample distribution:")
for category, count in categories.items():
    print(f"{category}: {count}")
