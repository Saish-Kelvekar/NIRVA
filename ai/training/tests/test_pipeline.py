"""Workflow tests for the NIRVA dataset pipeline.

Covers the review manifest, approved_dataset.py, check_drafts.py and
prepare_final_dataset.py: approved / rejected / unreviewed examples,
stale approvals, accidental answer mismatches vs reviewed edits,
duplicates, and system-prompt consistency.

Every test runs on temporary copies of the real data files. The files in
data/ are never modified. Review decisions in the copied manifest are reset
to "unreviewed" first, so the tests do not depend on how far the real
review has progressed.

Usage (from the project root):
    ai/.venv/Scripts/python.exe ai/training/tests/test_pipeline.py

Exit status: 0 when all tests pass, 1 otherwise.
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
TRAIN = ROOT / "ai" / "training"
PY = sys.executable

results = []
WORK = None  # set in main()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(script, *args):
    p = subprocess.run([PY, str(TRAIN / script), *map(str, args)], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def check(name, cond, out=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)
    if not cond and out:
        print(out)


def rjsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def wjsonl(path, records):
    Path(path).write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


def rjson(path):
    return json.load(open(path, encoding="utf-8"))


def wjson(path, data):
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False)


def setup():
    """Fresh temp copy of the data, with every review decision reset."""
    d = Path(tempfile.mkdtemp(dir=WORK))
    for name in ("raw_facts.json", "generated_drafts.jsonl", "train.jsonl"):
        shutil.copy(DATA / name, d / name)
    manifest = rjson(DATA / "review_manifest.json")
    for entry in manifest["examples"]:
        entry.update(decision="unreviewed", reviewer="", reviewed_on="")
    wjson(d / "manifest.json", manifest)
    return d


def mset(d, decision, *ids, reviewer="Tester"):
    return run("review_manifest.py", "--manifest", d / "manifest.json", "--drafts", d / "generated_drafts.jsonl",
               "set", "--decision", decision, "--reviewer", reviewer, *ids)


def approve(d, *extra):
    return run("approved_dataset.py", "--drafts", d / "generated_drafts.jsonl", "--manifest", d / "manifest.json",
               "--facts", d / "raw_facts.json", "--output", d / "approved.jsonl", *extra)


def final(d, *extra):
    args = ["--approved", d / "approved.jsonl", "--original", d / "train.jsonl",
            "--manifest", d / "manifest.json", "--facts", d / "raw_facts.json", "--output", d / "final.jsonl"]
    return run("prepare_final_dataset.py", *args, *extra)


def check_drafts(d):
    return run("check_drafts.py", "--drafts", d / "generated_drafts.jsonl", "--manifest", d / "manifest.json",
               "--facts", d / "raw_facts.json")


def edit_manifest(d, example_id, **changes):
    manifest = rjson(d / "manifest.json")
    for entry in manifest["examples"]:
        if entry["example_id"] == example_id:
            entry.update(changes)
    wjson(d / "manifest.json", manifest)


def draft_index(drafts, question):
    return next(i for i, r in enumerate(drafts) if r["messages"][1]["content"] == question)


# ---------------------------------------------------------------------------
# Pick test examples from the real data
# ---------------------------------------------------------------------------

def pick_examples():
    facts = {f["id"]: f for f in rjson(DATA / "raw_facts.json")}
    entries = rjson(DATA / "review_manifest.json")["examples"]

    def verified(e):
        return facts.get(e["source_fact_id"], {}).get("status") == "verified"

    exact = [e for e in entries
             if verified(e) and not e["answer_edit_reason"]
             and e["answer"] == facts[e["source_fact_id"]]["fact"]]
    edits = [e for e in entries if verified(e) and e["answer_edit_reason"]]
    unverified = [e for e in entries if not verified(e)]

    if len(exact) < 4:
        sys.exit("Test setup: need at least 4 drafts with verified facts and exact answers.")
    return {
        "A1": exact[0], "A2": exact[1], "REJ": exact[2], "UNREV": exact[3],
        "EDIT": edits[0] if edits else None,
        "UNVER": unverified[0] if unverified else None,
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_approval(x):
    print("== Approval workflow ==")
    A1, A2, REJ, UNREV = (x[k]["example_id"] for k in ("A1", "A2", "REJ", "UNREV"))
    EDIT = x["EDIT"]["example_id"] if x["EDIT"] else None
    UNVER = x["UNVER"]["example_id"] if x["UNVER"] else None

    d = setup()
    to_approve = [i for i in (A1, A2, EDIT, UNVER) if i]
    mset(d, "approved", *to_approve)
    mset(d, "rejected", REJ)
    code, out = approve(d)
    got = {r["example_id"] for r in rjsonl(d / "approved.jsonl")} if code == 0 else set()
    expected = {i for i in (A1, A2, EDIT) if i}
    check("approved examples are written", code == 0 and got == expected, out)
    check("rejected example excluded", REJ not in got)
    check("unreviewed example excluded", UNREV not in got)
    check("only explicitly approved drafts are output", len(got) == len(expected))
    if EDIT:
        check("approved reviewed answer edit is accepted", EDIT in got, out)
    if UNVER:
        check("approved example on non-verified fact excluded with warning",
              UNVER not in got and "WARNING" in out and UNVER in out, out)
    if code == 0:
        recs = rjsonl(d / "approved.jsonl")
        check("output: canonical prompt, status approved",
              all(r["status"] == "approved" for r in recs) and len({r["messages"][0]["content"] for r in recs}) == 1)
    code, out = approve(d)
    check("existing output not overwritten without --overwrite", code == 1 and "--overwrite" in out, out)

    d = setup()
    code, out = approve(d)
    check("zero approvals -> nothing written, exit 1", code == 1 and not (d / "approved.jsonl").exists(), out)

    d = setup()
    mset(d, "approved", A1)
    drafts = rjsonl(d / "generated_drafts.jsonl")
    drafts[draft_index(drafts, x["A1"]["question"])]["messages"][2]["content"] += " Extra unsupported detail."
    wjsonl(d / "generated_drafts.jsonl", drafts)
    code, out = approve(d)
    check("draft edited after approval -> error (stale hash)", code == 1 and "changed after approval" in out, out)

    d = setup()
    code, out = mset(d, "approved", A1, reviewer="")
    check("CLI approval without reviewer refused", code == 1 and "--reviewer is required" in out, out)
    edit_manifest(d, A1, decision="approved")
    code, out = approve(d)
    check("hand-edited approval missing reviewer/date -> error", code == 1 and "needs a reviewer" in out, out)

    d = setup()
    edit_manifest(d, A1, decision="yes")
    code, out = approve(d)
    check("invalid decision value -> error", code == 1 and "invalid decision" in out, out)

    d = setup()
    mset(d, "approved", A1)
    drafts = rjsonl(d / "generated_drafts.jsonl")
    wjsonl(d / "generated_drafts.jsonl", drafts + [drafts[0]])
    code, out = approve(d)
    check("duplicate example ID in drafts -> error", code == 1 and "duplicate example_id" in out, out)

    d = setup()
    mset(d, "approved", A1)
    drafts = rjsonl(d / "generated_drafts.jsonl")
    drafts[0]["messages"][0]["content"] = "You are a generic chatbot."
    wjsonl(d / "generated_drafts.jsonl", drafts)
    code, out = approve(d)
    check("unknown system prompt in drafts -> error", code == 1 and "unknown system prompt" in out, out)


def test_check_drafts(x):
    print("== Accidental mismatch vs reviewed edit (check_drafts) ==")
    d = setup()
    code, out = check_drafts(d)
    check("check_drafts passes on unmodified copy", code == 0, out)

    drafts = rjsonl(d / "generated_drafts.jsonl")
    drafts[draft_index(drafts, x["A1"]["question"])]["messages"][2]["content"] = "Dandeli is in Goa."
    wjsonl(d / "generated_drafts.jsonl", drafts)
    code, out = check_drafts(d)
    fact_id = x["A1"]["source_fact_id"]
    check("accidental answer mismatch -> error, exit 1",
          code == 1 and f"answer differs from source fact {fact_id}" in out, out)
    if x["EDIT"]:
        check("reviewed answer edits reported as intentional",
              "Reviewed answer edits" in out and x["EDIT"]["example_id"] in out, out)

        d = setup()
        drafts = rjsonl(d / "generated_drafts.jsonl")
        drafts[draft_index(drafts, x["EDIT"]["question"])]["messages"][2]["content"] = "Changed later."
        wjsonl(d / "generated_drafts.jsonl", drafts)
        code, out = check_drafts(d)
        check("edit reason does not cover a later change to the answer",
              code == 1 and "changed after it was recorded" in out, out)

    d = setup()
    drafts = rjsonl(d / "generated_drafts.jsonl")
    drafts[1]["messages"][1]["content"] = drafts[0]["messages"][1]["content"].upper() + "  "
    wjsonl(d / "generated_drafts.jsonl", drafts)
    code, out = check_drafts(d)
    check("duplicate question (case/space-insensitive) -> error", code == 1 and "duplicate question" in out, out)


def test_final(x):
    print("== Final dataset preparation ==")
    A1, A2 = x["A1"]["example_id"], x["A2"]["example_id"]
    d = setup()
    mset(d, "approved", A1, A2)
    approve(d)
    orig_b = [r for r in rjsonl(d / "train.jsonl") if r["source_fact_id"].startswith("BEHAVIOUR")]
    code, out = final(d)
    fin = rjsonl(d / "final.jsonl") if code == 0 else []
    check("final build succeeds: approved + behaviour", code == 0 and len(fin) == 2 + len(orig_b), out)
    check("single canonical system prompt in final", len({r["messages"][0]["content"] for r in fin}) == 1)
    legacy = sum(1 for r in orig_b if r["messages"][0]["content"] != fin[0]["messages"][0]["content"]) if fin else -1
    check("legacy behaviour prompts migrated", f"Legacy system prompts migrated: {legacy}" in out, out)
    fin_b = [r for r in fin if r["source_fact_id"].startswith("BEHAVIOUR")]
    check("behaviour questions/answers unchanged by migration",
          [r["messages"][1:] for r in orig_b] == [r["messages"][1:] for r in fin_b])
    check("no status field; every record has example_id", all("status" not in r and r.get("example_id") for r in fin))

    recs = rjsonl(d / "approved.jsonl")
    wjsonl(d / "approved_bad.jsonl", recs + [dict(recs[0], example_id="FACT001-ffffffff")])
    code, out = run("prepare_final_dataset.py", "--approved", d / "approved_bad.jsonl", "--original", d / "train.jsonl",
                    "--manifest", d / "manifest.json", "--facts", d / "raw_facts.json", "--output", d / "f2.jsonl")
    check("record not approved in manifest -> error", code == 1 and "not approved in the review manifest" in out, out)

    legacy_file = d / "legacy_approved.jsonl"
    wjsonl(legacy_file, [{k: v for k, v in r.items() if k != "example_id"} for r in recs])
    code, out = run("prepare_final_dataset.py", "--approved", legacy_file, "--original", d / "train.jsonl",
                    "--manifest", d / "manifest.json", "--facts", d / "raw_facts.json", "--output", d / "f4.jsonl")
    check("approved records without example_id (old auto-approval format) rejected",
          code == 1 and "missing example_id" in out, out)

    train = rjsonl(d / "train.jsonl")
    next(r for r in train if r["source_fact_id"].startswith("BEHAVIOUR"))["messages"][1]["content"] = x["A1"]["question"]
    wjsonl(d / "train.jsonl", train)
    code, out = final(d, "--output", d / "f3.jsonl")
    check("duplicate question across knowledge/behaviour -> error", code == 1 and "duplicate question" in out, out)

    d = setup(); mset(d, "approved", A1); approve(d)
    train = rjsonl(d / "train.jsonl")
    next(r for r in train if r["source_fact_id"].startswith("BEHAVIOUR"))["messages"][0]["content"] = "Unknown prompt"
    wjsonl(d / "train.jsonl", train)
    code, out = final(d)
    check("unknown behaviour prompt not migrated -> error", code == 1 and "unknown system prompt" in out, out)

    d = setup(); mset(d, "approved", A1); approve(d)
    facts = rjson(d / "raw_facts.json")
    next(f for f in facts if f["id"] == x["A1"]["source_fact_id"])["status"] = "needs_review"
    wjson(d / "raw_facts.json", facts)
    code, out = final(d)
    check("fact downgraded after approval -> final build refuses", code == 1 and "not verified" in out, out)


def test_sync(x):
    print("== Manifest sync ==")
    A1 = x["A1"]["example_id"]
    d = setup()
    edit_manifest(d, A1, decision="approved", reviewer="T", reviewed_on="2026-11-19")
    drafts = rjsonl(d / "generated_drafts.jsonl")
    drafts[draft_index(drafts, x["A1"]["question"])]["messages"][2]["content"] = "Changed."
    wjsonl(d / "generated_drafts.jsonl", drafts)
    before = rjson(d / "manifest.json")
    code, out = run("review_manifest.py", "--manifest", d / "manifest.json", "--drafts", d / "generated_drafts.jsonl", "sync")
    after = rjson(d / "manifest.json")
    entry = next(e for e in after["examples"] if e["example_id"] == A1)
    check("sync leaves approved entry untouched and reports STALE",
          "STALE" in out and entry["answer"] != "Changed." and entry["decision"] == "approved", out)
    check("sync adds nothing new and never approves",
          len(after["examples"]) == len(before["examples"])
          and sum(e["decision"] == "approved" for e in after["examples"]) == 1)


def main():
    global WORK
    with tempfile.TemporaryDirectory(prefix="nirva_tests_") as tmp:
        WORK = tmp
        examples = pick_examples()
        test_approval(examples)
        test_check_drafts(examples)
        test_final(examples)
        test_sync(examples)

    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} tests passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
