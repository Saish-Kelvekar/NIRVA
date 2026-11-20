"""Generate question-answer drafts from verified NIRVA facts.

Only facts with status "verified" are used. The assistant answer is the
fact text copied word for word, so drafts never add unsupported details.
Every draft is marked "needs_review" and must be checked by a person
before approved_dataset.py is run.

Drafts whose example_id or question already exists in an existing draft
file (default: data/generated_drafts.jsonl) are skipped, so a new output
file holds only new examples and reviewed drafts are never replaced.

Usage:
    python ai/training/generate_dataset.py --dry-run
    python ai/training/generate_dataset.py --output data/new_drafts.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

from pipeline_common import (
    CANONICAL_SYSTEM_PROMPT,
    example_id_of,
    load_jsonl,
    make_example_id,
    question_of,
)
from validate_facts import normalise_text, validate_facts

PROJECT_DIR = Path(__file__).resolve().parents[2]

FACTS_PATH = PROJECT_DIR / "data" / "raw_facts.json"
OUTPUT_PATH = PROJECT_DIR / "data" / "generated_drafts.jsonl"

# Canonical prompt shared by the whole pipeline (see pipeline_common.py).
SYSTEM_PROMPT = CANONICAL_SYSTEM_PROMPT

# Questions are written specifically for each verified fact.
QUESTION_TEMPLATES = {
    "FACT001": [
        "Where is Dandeli located?",
        "Which district does Dandeli belong to?"
    ],
    "FACT002": [
        "Which river flows through Dandeli Wildlife Sanctuary?",
        "What river is associated with Dandeli Wildlife Sanctuary?"
    ],
    "FACT003": [
        "Which tiger reserve includes Dandeli Wildlife Sanctuary?",
        "Is Dandeli Wildlife Sanctuary part of Kali Tiger Reserve?"
    ],
    "FACT004": [
        "What activities can tourists enjoy in Dandeli?",
        "What adventure and nature activities are associated with Dandeli?"
    ],
    "FACT005": [
        "What types of wildlife and birds are found in Dandeli Wildlife Sanctuary?",
        "Are hornbills found in Dandeli Wildlife Sanctuary?"
    ],
    "FACT006": [
        "When was Dandeli Wildlife Sanctuary declared a wildlife sanctuary?",
        "In which year was Dandeli Wildlife Sanctuary declared a sanctuary?"
    ],
    "FACT007": [
        "Which protected areas are part of Kali Tiger Reserve?",
        "What is the relationship between Dandeli Wildlife Sanctuary and Anshi National Park?"
    ],
    "FACT008": [
        "Which animals are found in Kali Tiger Reserve?",
        "What wildlife does Kali Tiger Reserve support?"
    ],
    "FACT009": [
        "How many South Indian hornbill species are visitors likely to see in Dandeli?",
        "What is notable about hornbill diversity in Dandeli?"
    ],
    "FACT010": [
        "What are Syntheri Rocks?",
        "What natural feature can visitors see at Syntheri Rocks?"
    ],
    "FACT011": [
        "What are Kavala Caves known for?",
        "What natural formations can be seen in Kavala Caves?"
    ],
    "FACT012": [
        "Where does white-water rafting take place in Dandeli?",
        "Which river is used for white-water rafting in Dandeli?"
    ],
    "FACT013": [
        "What factors affect rafting operations in Dandeli?",
        "Does rafting availability in Dandeli depend on river flow and permissions?"
    ],
    "FACT014": [
        "Which railway station is identified for reaching Dandeli?",
        "Can travellers use Alnavar Junction to reach Dandeli?"
    ],
    "FACT015": [
        "Where can visitors enjoy kayaking in Dandeli?",
        "Which river is associated with kayaking in Dandeli?"
    ]
}


def select_verified_facts(facts):
    """Return verified facts; report every fact that is left out."""
    selected = []
    for fact in facts:
        status = fact.get("status")
        if status == "verified":
            selected.append(fact)
        else:
            print(f"Skipping {fact.get('id')}: status is {status!r}, not 'verified'")
    return selected


def generate_examples(facts):
    examples = []
    seen_questions = {}
    duplicate_errors = []

    for fact in facts:
        fact_id = fact["id"]
        answer = fact["fact"]

        questions = QUESTION_TEMPLATES.get(fact_id, [])

        if not questions:
            print(f"Warning: No question templates for {fact_id}")
            continue

        for question in questions:
            key = normalise_text(question)
            if key in seen_questions:
                duplicate_errors.append(
                    f"Duplicate question for {fact_id} "
                    f"(already used by {seen_questions[key]}): {question}"
                )
                continue
            seen_questions[key] = fact_id

            examples.append({
                "messages": [
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT.strip()
                    },
                    {
                        "role": "user",
                        "content": question
                    },
                    {
                        "role": "assistant",
                        "content": answer
                    }
                ],
                "source_fact_id": fact_id,
                "example_id": make_example_id(fact_id, question),
                "status": "needs_review"
            })

    return examples, duplicate_errors


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--facts", type=Path, default=FACTS_PATH,
                        help="Fact file (default: data/raw_facts.json)")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH,
                        help="Draft output file (default: data/generated_drafts.jsonl)")
    parser.add_argument("--overwrite", action="store_true",
                        help="Allow replacing an existing output file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be generated without writing a file")
    parser.add_argument("--existing", type=Path, action="append",
                        help="Existing draft file whose examples are skipped; repeatable "
                             "(default: data/generated_drafts.jsonl)")
    parser.add_argument("--include-existing", action="store_true",
                        help="Do not skip examples already present in existing draft files")
    return parser.parse_args(argv)


def existing_keys(paths, output):
    """Example IDs and normalised questions already present in other draft files."""
    ids, questions = set(), set()
    for path in paths:
        path = path.resolve()
        if path == output or not path.exists():
            continue
        for _, record in load_jsonl(path):
            ids.add(example_id_of(record))
            questions.add(normalise_text(question_of(record)))
    return ids, questions


def main(argv=None):
    args = parse_args(argv)

    with open(args.facts, "r", encoding="utf-8") as file:
        facts = json.load(file)

    fact_errors, _ = validate_facts(facts)
    if fact_errors:
        print("Fact file failed validation; no drafts generated.")
        for error in fact_errors:
            print("-", error)
        print("Run ai/training/validate_facts.py for the full report.")
        return 1

    known_ids = {fact["id"] for fact in facts}
    for fact_id in QUESTION_TEMPLATES:
        if fact_id not in known_ids:
            print(f"Warning: Question templates exist for unknown fact {fact_id}")

    verified = select_verified_facts(facts)
    examples, duplicate_errors = generate_examples(verified)

    if duplicate_errors:
        print("Duplicate questions found; no drafts written.")
        for error in duplicate_errors:
            print("-", error)
        return 1

    # Skip drafts that already exist elsewhere, so reviewed or hand-corrected
    # drafts are never duplicated or replaced by a fresh copy.
    output = args.output.resolve()
    skipped = 0
    if not args.include_existing:
        # The output file only stops counting as 'existing' when it is being replaced.
        ignore = output if args.overwrite else None
        ids, questions = existing_keys(args.existing or [OUTPUT_PATH], ignore)
        kept = []
        for example in examples:
            if (example["example_id"] in ids
                    or normalise_text(question_of(example)) in questions):
                skipped += 1
            else:
                kept.append(example)
        examples = kept

    print("Facts in file:", len(facts))
    print("Verified facts processed:", len(verified))
    print("Skipped (already in existing drafts):", skipped)
    print("New draft examples:", len(examples))

    if not examples:
        print("Nothing new to generate; no file written.")
        return 0

    if args.dry_run:
        print("Dry run: no file written.")
        return 0

    if output.exists() and not args.overwrite:
        print(f"Output already exists: {output}")
        print("Use --output for a new file, or --overwrite to replace it.")
        return 1

    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as file:
        for example in examples:
            file.write(
                json.dumps(example, ensure_ascii=False) + "\n"
            )

    print("Draft generation completed!")
    print("Output:", output)
    print("All drafts are marked needs_review. Review them before approval.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
