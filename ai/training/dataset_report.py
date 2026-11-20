"""Human-readable quality report for a NIRVA dataset (advisory only).

Runs every check in quality_checks.py and prints a report that helps decide
whether the dataset is ready to scale. It never modifies, removes or
approves anything. By default it writes nothing; --json writes a
machine-readable copy to a NEW file (it refuses to overwrite).

Usage:
    python ai/training/dataset_report.py                       # data/final_train.jsonl
    python ai/training/dataset_report.py --dataset data/generated_drafts.jsonl
    python ai/training/dataset_report.py --json report.json

--kind (drafts | approved | final) controls how strict traceability is.
By default it is inferred from the file name ("draft" -> drafts,
"approved" -> approved, otherwise final).

Exit status: 0 when the report was produced (even with warnings),
2 when an input file cannot be read.
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

import quality_checks as qc
from pipeline_common import DATA_DIR, FACTS_PATH, FINAL_PATH, MANIFEST_PATH

EVAL_PATH = DATA_DIR / "nirva_eval.json"

SECTIONS = (
    ("input", "Input problems"),
    ("behaviour_share", "Behaviour share"),
    ("fact_balance", "Examples per fact"),
    ("exact_duplicate", "Exact duplicates"),
    ("near_duplicate", "Near-duplicate questions"),
    ("unsupported_entity", "Unsupported entity indicators"),
    ("repeated_answer", "Repeated answers"),
    ("eval_overlap", "Evaluation overlap"),
    ("traceability", "Traceability"),
)


def infer_kind(path):
    name = Path(path).name.lower()
    if "draft" in name:
        return "drafts"
    if "approved" in name:
        return "approved"
    return "final"


def short_sha(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    except OSError:
        return "missing"


def build_report(dataset, facts_path=FACTS_PATH, manifest_path=MANIFEST_PATH, eval_path=EVAL_PATH, kind=None):
    """Run all checks. Raises FileNotFoundError if the dataset is missing."""
    kind = kind or infer_kind(dataset)
    examples, findings = qc.load_examples(dataset)

    facts, problem = qc.load_json_or_none(facts_path)
    findings += [problem] if problem else []
    manifest, problem = qc.load_json_or_none(manifest_path)
    findings += [problem] if problem else []

    eval_questions = []
    if eval_path is not None and Path(eval_path).exists():
        eval_questions, problems = qc.load_eval_questions(eval_path)
        findings += problems

    share, share_findings = qc.behaviour_share(examples, dataset_kind=kind)
    distribution, dist_findings = qc.answer_distribution(examples, facts)
    eval_rows, eval_findings = qc.eval_overlap(examples, eval_questions)
    findings += share_findings + dist_findings
    findings += qc.exact_duplicates(examples)
    findings += qc.near_duplicates(examples)
    findings += qc.unsupported_entities(examples, facts) if facts is not None else []
    findings += eval_findings
    findings += qc.traceability(examples, facts, manifest, kind)

    facts_index = qc.facts_by_id(facts)
    return {
        "dataset": str(dataset),
        "kind": kind,
        "inputs": {name: {"path": str(p), "sha256_12": short_sha(p) if p else "not given"}
                   for name, p in (("dataset", dataset), ("facts", facts_path),
                                   ("manifest", manifest_path), ("eval", eval_path))},
        "inputs_used": {"facts": facts is not None, "manifest": manifest is not None,
                        "eval_questions": len(eval_questions)},
        "thresholds": qc.THRESHOLDS,
        "summary": share,
        "fact_status": {fid: f.get("status") for fid, f in facts_index.items()},
        "distribution": distribution,
        "eval_rows": eval_rows,
        "findings": findings,
    }


# ---------------------------------------------------------------------------
# Text rendering
# ---------------------------------------------------------------------------

def render(report):
    out = []
    add = out.append
    s = report["summary"]
    d = report["distribution"]
    findings = report["findings"]
    warnings = [f for f in findings if f["severity"] == "warning"]

    add("=" * 72)
    add("NIRVA DATASET QUALITY REPORT (advisory: nothing is changed or removed)")
    add("=" * 72)
    add(f"Dataset: {report['dataset']}  (checked as: {report['kind']})")
    for name, info in report["inputs"].items():
        add(f"  {name:<9} {info['sha256_12']}  {info['path']}")
    used = report["inputs_used"]
    add(f"  facts loaded: {used['facts']}, manifest loaded: {used['manifest']}, "
        f"eval questions: {used['eval_questions']}")

    add("\n1. SUMMARY")
    total = s["total"]
    pct = (lambda n: f"{n / total:.0%}") if total else (lambda n: "-")
    add(f"  Total examples:     {total}")
    if s["behaviour_share_applicable"]:
        add(f"  Knowledge:          {s['knowledge']} ({pct(s['knowledge'])})")
        add(f"  Behaviour:          {s['behaviour']} ({pct(s['behaviour'])})   target "
            f"{qc.THRESHOLDS['behaviour_share_min']:.0%}-{qc.THRESHOLDS['behaviour_share_max']:.0%}")
    else:
        add(f"  Knowledge:          {s['knowledge']}")
        add(f"  Behaviour share:    {s['behaviour_share_note']}")
    add(f"  Distinct answers:   {d['distinct_answers']}")
    add(f"  Warnings: {len(warnings)}   Info notes: {len(findings) - len(warnings)}")

    add("\n2. EXAMPLES PER SOURCE")
    status = report["fact_status"]
    add(f"  {'Source':<14}{'Examples':>9}  Fact status")
    for source_id, count in d["examples_per_source"].items():
        label = status.get(source_id, "behaviour" if source_id.startswith("BEHAVIOUR") else "UNKNOWN")
        add(f"  {source_id or '(missing)':<14}{count:>9}  {label}")
    for fid in d["verified_facts_without_examples"]:
        add(f"  {fid:<14}{0:>9}  verified  <- no examples")
    add(f"  Median examples per knowledge fact: {d['knowledge_median_per_fact']}")

    add("\n3. ANSWER DISTRIBUTION")
    for unit, key in (("words", "answer_words"), ("characters", "answer_chars")):
        for kind, st in d[key].items():
            if st["count"]:
                add(f"  {kind:<10} answer {unit:<10} min {st['min']:>4}  median {st['median']:>6}  "
                    f"mean {st['mean']:>6}  max {st['max']:>4}  (n={st['count']})")
    q = d["question_words"]
    if q["count"]:
        add(f"  questions  words      min {q['min']:>4}  median {q['median']:>6}  mean {q['mean']:>6}  max {q['max']:>4}")
    if d["repeated_answers"]:
        add(f"  Answer texts used more than once: {len(d['repeated_answers'])}")
        for r in d["repeated_answers"]:
            add(f"    x{r['count']}  {', '.join(r['source_ids'])}: {r['answer'][:70]}{'...' if len(r['answer']) > 70 else ''}")
    else:
        add("  No answer text is used more than once.")

    add("\n4. EVALUATION OVERLAP (closest training question for each eval question)")
    if not report["eval_rows"]:
        add("  No evaluation questions loaded.")
    for r in report["eval_rows"]:
        flag = {"exact": "EXACT", "near": "NEAR ", "none": "  -  "}[r["status"]]
        add(f"  [{flag}] eval {r['eval_id']} ({r['category']}) char {r['char_similarity']:.2f} "
            f"word {r['word_similarity']:.2f}")
        add(f"          eval:  {r['question']}")
        add(f"          train: {r['closest_question']}  [{r['closest_id']}]")
    add("  Note: only wording is compared. Questions that ask the same thing in different")
    add("  words (e.g. the same refusal topic) are not detected.")

    add("\n5. FINDINGS BY CHECK")
    for check, title in SECTIONS:
        items = [f for f in findings if f["check"] == check]
        if not items:
            add(f"  {title}: none")
            continue
        n_warn = sum(f["severity"] == "warning" for f in items)
        add(f"  {title}: {n_warn} warning(s), {len(items) - n_warn} info")
        for f in items:
            add(f"    - [{f['severity']}] {f['message']}")
            if f["ids"] and len(f["ids"]) <= 6:
                add(f"        ids: {', '.join(f['ids'])}")
            elif f["ids"]:
                add(f"        ids: {', '.join(f['ids'][:6])} ... (+{len(f['ids']) - 6})")

    add("\n6. WARNINGS REQUIRING HUMAN REVIEW")
    if not warnings:
        add("  None.")
    for number, f in enumerate(warnings, start=1):
        add(f"  {number:>2}. [{f['check']}] {f['message']}")

    add("\nThresholds are provisional (calibrated on 30 baseline drafts):")
    t = qc.THRESHOLDS
    add(f"  near-duplicate: same source char >= {t['same_fact_char']} or content-word >= {t['same_fact_word']}; "
        f"different source char >= {t['cross_fact_char']}")
    add(f"  eval overlap: char >= {t['eval_char']} or content-word >= {t['eval_word']}; "
        f"repeated answer > {t['max_identical_answer']}; fact > {t['fact_overrepresented_ratio']}x median")
    add("Every finding is advisory. Nothing was modified.")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------

def parse_args(argv):
    parser = argparse.ArgumentParser(description="Advisory quality report for a NIRVA dataset.")
    parser.add_argument("--dataset", type=Path, default=FINAL_PATH)
    parser.add_argument("--facts", type=Path, default=FACTS_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--eval", type=Path, default=EVAL_PATH)
    parser.add_argument("--kind", choices=("drafts", "approved", "final"))
    parser.add_argument("--json", type=Path, help="Also write the report as JSON to this NEW file")
    return parser.parse_args(argv)


def main(argv=None):
    # UTF-8 even when piped or redirected (Windows would otherwise use the
    # legacy code page and garble non-ASCII text such as the em dash).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    args = parse_args(argv)
    if not args.dataset.exists():
        print(f"Dataset not found: {args.dataset}")
        return 2
    if args.json and args.json.exists():
        print(f"Refusing to overwrite existing file: {args.json}")
        return 2
    try:
        report = build_report(args.dataset, args.facts, args.manifest, args.eval, args.kind)
    except (OSError, UnicodeDecodeError) as error:
        print(f"Could not read input: {error}")
        return 2
    print(render(report), end="")
    if args.json:
        args.json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"JSON report written to {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
