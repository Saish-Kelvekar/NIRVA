"""Golden, snapshot and compatibility tests for the NIRVA dataset pipeline.

Pins the Stage 0 baseline (2026-11-20) so later pipeline changes cannot
silently alter it:

  Golden      make_example_id(), content_hash() and normalise_text() return
              exactly the values recorded in fixtures/<baseline>/golden.json
              for every real example (30 drafts + 3 behaviour examples).
  Snapshot    approved_dataset.py and prepare_final_dataset.py, run on copies
              of the frozen baseline inputs, produce byte-identical output to
              the frozen baseline outputs.
  Manifest    The 30 baseline manifest entries stay compatible: 28 approved,
              2 rejected, 0 stale, 0 orphaned, and entries without optional
              fields (old format) still work.
  Live        The current data/ files are consistent: every baseline draft and
              manifest entry is still present and unchanged, and the
              approved/final files equal a fresh rebuild of the current data.
  Integrity   The checksum helper used by run_all.py detects changed, added
              and removed files.

Frozen fixtures live in fixtures/baseline_2026-11-20/ and are checked
against SHA256SUMS.json before use. Never edit them by hand; a failure here
means pipeline behaviour or the data changed and must be investigated.

Every script runs on temporary copies. Nothing in data/ or in the fixtures
is written.

Usage (from the project root):
    ai/.venv/Scripts/python.exe ai/training/tests/test_golden.py

Exit status: 0 when all tests pass, 1 otherwise.
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DATA = ROOT / "data"
TRAIN = ROOT / "ai" / "training"
FIXTURES = Path(__file__).resolve().parent / "fixtures" / "baseline_2026-11-20"
PY = sys.executable

sys.dont_write_bytecode = True
sys.path.insert(0, str(TRAIN))
from pipeline_common import content_hash, make_example_id  # noqa: E402
from validate_facts import normalise_text  # noqa: E402

# Fields a manifest entry had before any optional metadata existed. The
# pipeline must keep accepting entries that carry only these.
MINIMAL_ENTRY_FIELDS = ("example_id", "decision", "reviewer", "reviewed_on", "content_hash")

results = []
WORK = None  # set in main()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(script, *args):
    p = subprocess.run([PY, "-B", str(TRAIN / script), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)
    if not cond and detail:
        print(ascii(detail) if not isinstance(detail, str) else detail.encode("ascii", "replace").decode())


def rjsonl(path):
    return [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]


def rjson(path):
    return json.load(open(path, encoding="utf-8"))


def same_bytes(a, b):
    """Byte-identical comparison.

    Pipeline scripts write in text mode, so line endings follow the platform
    (CRLF on Windows, where the baseline was recorded). On another platform
    the comparison ignores only that difference.
    """
    x, y = Path(a).read_bytes(), Path(b).read_bytes()
    if os.linesep != "\r\n":
        x, y = x.replace(b"\r\n", b"\n"), y.replace(b"\r\n", b"\n")
    return x == y


def tree_checksums(root):
    """{relative path: sha256} for every file under root."""
    root = Path(root)
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


def diff_checksums(before, after):
    """Return (changed, added, removed) path lists."""
    changed = sorted(p for p in before.keys() & after.keys() if before[p] != after[p])
    return changed, sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())


def workdir(source):
    """Fresh temp copy of the pipeline inputs from `source` (fixtures or data/)."""
    d = Path(tempfile.mkdtemp(dir=WORK))
    for name in ("raw_facts.json", "generated_drafts.jsonl", "review_manifest.json",
                 "train.jsonl", "approved_train.jsonl", "final_train.jsonl"):
        shutil.copy2(source / name, d / name)
    return d


def build_approved(d, manifest="review_manifest.json", output="approved.out.jsonl", *extra):
    return run("approved_dataset.py", "--drafts", d / "generated_drafts.jsonl", "--manifest", d / manifest,
               "--facts", d / "raw_facts.json", "--output", d / output, *extra)


def build_final(d, approved, manifest="review_manifest.json", output="final.out.jsonl", *extra):
    return run("prepare_final_dataset.py", "--approved", d / approved, "--original", d / "train.jsonl",
               "--manifest", d / manifest, "--facts", d / "raw_facts.json", "--output", d / output, *extra)


def manifest_status(d, manifest="review_manifest.json"):
    """Parse review_manifest.py status output into a dict of counts."""
    code, out = run("review_manifest.py", "--manifest", d / manifest,
                    "--drafts", d / "generated_drafts.jsonl", "status")
    labels = {
        "approved:": "approved", "rejected:": "rejected", "unreviewed:": "unreviewed",
        "Drafts not yet in manifest:": "missing",
        "Stale entries (draft changed since entry):": "stale",
        "Entries with no matching draft:": "orphaned",
        "Entries:": "entries",
    }
    counts = {}
    for line in out.splitlines():
        text = line.strip()
        for label, key in labels.items():
            if text.startswith(label):
                counts[key] = int(text[len(label):].strip())
                break
    return code, counts, out


# ---------------------------------------------------------------------------
# Fixture integrity (runs first: every other test trusts the fixtures)
# ---------------------------------------------------------------------------

def test_fixture_integrity():
    print("== Fixture integrity ==")
    expected = rjson(FIXTURES / "SHA256SUMS.json")
    actual = {name: hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
              for name in expected if (FIXTURES / name).exists()}
    check("baseline fixtures match SHA256SUMS.json", actual == expected,
          f"mismatched: {[n for n in expected if actual.get(n) != expected[n]]}")
    return actual == expected


# ---------------------------------------------------------------------------
# Golden values
# ---------------------------------------------------------------------------

def test_golden(golden):
    print("== Golden values ==")
    cases = golden["normalise_text_cases"]
    bad = [c["input"] for c in cases if normalise_text(c["input"]) != c["output"]]
    check(f"normalise_text: {len(cases)} pinned edge cases", not bad, f"changed for: {bad}")

    # Synthetic inputs (not training data): the real examples are all ASCII,
    # so these pin how non-ASCII, quotes, control characters and empty
    # strings are encoded before hashing.
    hash_cases = golden["hash_cases"]
    bad = [ascii(c["question"]) for c in hash_cases
           if make_example_id(c["source_fact_id"], c["question"]) != c["example_id"]
           or content_hash(c["source_fact_id"], c["question"], c["answer"]) != c["content_hash"]]
    check(f"make_example_id/content_hash: {len(hash_cases)} pinned non-ASCII/edge inputs", not bad,
          f"changed for: {bad}")

    examples = golden["examples"]
    check("golden set covers 30 drafts + 3 behaviour examples",
          Counter(e["origin"] for e in examples) == {"generated_drafts.jsonl": 30, "train.jsonl": 3})

    bad = [e["example_id"] for e in examples if normalise_text(e["question"]) != e["normalised_question"]]
    check("normalise_text: all 33 real questions", not bad, f"changed for: {bad}")

    bad = [e["example_id"] for e in examples if make_example_id(e["source_fact_id"], e["question"]) != e["example_id"]]
    check("make_example_id: all 33 real examples", not bad, f"changed for: {bad}")

    bad = [e["example_id"] for e in examples
           if content_hash(e["source_fact_id"], e["question"], e["answer"]) != e["content_hash"]]
    check("content_hash: all 33 real examples", not bad, f"changed for: {bad}")

    # The golden values must agree with the independently stored records.
    drafts = rjsonl(FIXTURES / "generated_drafts.jsonl")
    pinned = {(e["source_fact_id"], e["question"], e["answer"]) for e in examples}
    check("golden examples are exactly the baseline drafts' text",
          {(r["source_fact_id"], r["messages"][1]["content"], r["messages"][2]["content"]) for r in drafts}
          <= pinned and len(drafts) == 30)

    manifest = {e["example_id"]: e for e in rjson(FIXTURES / "review_manifest.json")["examples"]}
    draft_golden = [e for e in examples if e["origin"] == "generated_drafts.jsonl"]
    check("golden IDs and hashes equal those stored in the baseline manifest",
          len(manifest) == 30 and all(manifest.get(e["example_id"], {}).get("content_hash") == e["content_hash"]
                                      for e in draft_golden))

    approved = rjsonl(FIXTURES / "approved_train.jsonl")
    check("baseline approved_train IDs equal golden approved_ids (22)",
          [r["example_id"] for r in approved] == golden["approved_ids"] and len(approved) == 22)
    final = rjsonl(FIXTURES / "final_train.jsonl")
    check("baseline final_train IDs equal golden final_ids (25)",
          [r["example_id"] for r in final] == golden["final_ids"] and len(final) == 25)


# ---------------------------------------------------------------------------
# Snapshots (frozen baseline inputs -> byte-identical outputs)
# ---------------------------------------------------------------------------

def test_snapshots():
    print("== Snapshot: frozen baseline ==")
    d = workdir(FIXTURES)
    code, out = build_approved(d)
    check("approved_dataset.py output is byte-identical to baseline approved_train.jsonl",
          code == 0 and same_bytes(d / "approved.out.jsonl", FIXTURES / "approved_train.jsonl"), out)

    code, out = build_final(d, "approved_train.jsonl")
    check("prepare_final_dataset.py output is byte-identical to baseline final_train.jsonl",
          code == 0 and same_bytes(d / "final.out.jsonl", FIXTURES / "final_train.jsonl"), out)
    check("baseline final build: 22 knowledge + 3 behaviour = 25",
          "Knowledge examples: 22" in out and "Behaviour examples: 3" in out and "Total examples: 25" in out, out)

    # A second run must give the same bytes (no ordering or timestamp drift).
    code, out = build_approved(d, "review_manifest.json", "approved.again.jsonl")
    check("approved build is deterministic across runs",
          code == 0 and same_bytes(d / "approved.again.jsonl", d / "approved.out.jsonl"), out)

    d = workdir(FIXTURES)
    code, out = build_approved(d, "review_manifest.json", "approved.dry.jsonl", "--dry-run")
    code2, out2 = build_final(d, "approved_train.jsonl", "review_manifest.json", "final.dry.jsonl", "--dry-run")
    check("--dry-run writes no output (approved and final)",
          code == 0 and code2 == 0 and not (d / "approved.dry.jsonl").exists()
          and not (d / "final.dry.jsonl").exists(), out + out2)


# ---------------------------------------------------------------------------
# Manifest compatibility
# ---------------------------------------------------------------------------

def test_manifest_compatibility(golden):
    print("== Manifest compatibility ==")
    d = workdir(FIXTURES)
    code, counts, out = manifest_status(d)
    check("baseline manifest: 30 entries, 28 approved, 2 rejected, 0 unreviewed",
          code == 0 and counts.get("entries") == 30 and counts.get("approved") == 28
          and counts.get("rejected") == 2 and counts.get("unreviewed") == 0, out)
    check("baseline manifest: 0 stale, 0 orphaned, 0 drafts missing",
          counts.get("stale") == 0 and counts.get("orphaned") == 0 and counts.get("missing") == 0, out)
    check("golden manifest decision counts unchanged",
          golden["manifest_decisions"] == {"approved": 28, "rejected": 2})

    # Old format: keep only the minimal fields (plus a non-empty edit reason,
    # which is what makes a reviewed edit valid).
    manifest = rjson(d / "review_manifest.json")
    minimal = []
    for entry in manifest["examples"]:
        slim = {k: entry[k] for k in MINIMAL_ENTRY_FIELDS}
        if entry.get("answer_edit_reason"):
            slim["answer_edit_reason"] = entry["answer_edit_reason"]
        minimal.append(slim)
    (d / "minimal.json").write_text(json.dumps({"examples": minimal}, ensure_ascii=False), encoding="utf-8")

    code, out = build_approved(d, "minimal.json", "approved.minimal.jsonl")
    check("minimal-field (old format) manifest: approved output byte-identical to baseline",
          code == 0 and same_bytes(d / "approved.minimal.jsonl", FIXTURES / "approved_train.jsonl"), out)
    code, out = build_final(d, "approved_train.jsonl", "minimal.json", "final.minimal.jsonl")
    check("minimal-field (old format) manifest: final output byte-identical to baseline",
          code == 0 and same_bytes(d / "final.minimal.jsonl", FIXTURES / "final_train.jsonl"), out)
    code, out = run("check_drafts.py", "--drafts", d / "generated_drafts.jsonl",
                    "--manifest", d / "minimal.json", "--facts", d / "raw_facts.json")
    check("minimal-field (old format) manifest: check_drafts passes", code == 0, out)
    code, counts, out = manifest_status(d, "minimal.json")
    check("minimal-field (old format) manifest: 0 stale, 0 orphaned",
          code == 0 and counts.get("stale") == 0 and counts.get("orphaned") == 0, out)

    before = {e["example_id"]: (e["decision"], e["content_hash"]) for e in minimal}
    code, out = run("review_manifest.py", "--manifest", d / "minimal.json",
                    "--drafts", d / "generated_drafts.jsonl", "sync")
    after = {e["example_id"]: (e["decision"], e["content_hash"]) for e in rjson(d / "minimal.json")["examples"]}
    check("sync on old-format manifest adds nothing and keeps every decision and hash",
          code == 0 and before == after and "Added as unreviewed: 0" in out, out)

    # Unknown extra fields (e.g. future optional metadata) are ignored.
    manifest = rjson(d / "review_manifest.json")
    for entry in manifest["examples"]:
        entry["future_optional_field"] = "ignored"
    (d / "extra.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    code, out = build_approved(d, "extra.json", "approved.extra.jsonl")
    check("manifest entries with extra unknown fields: approved output byte-identical",
          code == 0 and same_bytes(d / "approved.extra.jsonl", FIXTURES / "approved_train.jsonl"), out)


# ---------------------------------------------------------------------------
# Live data consistency (current data/, read through temp copies)
# ---------------------------------------------------------------------------

def test_live(golden):
    print("== Live data consistency ==")
    draft_golden = {e["example_id"]: e for e in golden["examples"] if e["origin"] == "generated_drafts.jsonl"}

    live_drafts = {}
    for r in rjsonl(DATA / "generated_drafts.jsonl"):
        sid, q, a = r["source_fact_id"], r["messages"][1]["content"], r["messages"][2]["content"]
        live_drafts[r.get("example_id") or make_example_id(sid, q)] = content_hash(sid, q, a)
    missing = [i for i in draft_golden if i not in live_drafts]
    changed = [i for i in draft_golden if i in live_drafts and live_drafts[i] != draft_golden[i]["content_hash"]]
    check("all 30 baseline drafts still present with unchanged IDs and hashes",
          not missing and not changed, f"missing={missing} changed={changed}")

    live_manifest = {e["example_id"]: e for e in rjson(DATA / "review_manifest.json")["examples"]}
    missing = [i for i in draft_golden if i not in live_manifest]
    changed = [i for i in draft_golden if i in live_manifest
               and live_manifest[i].get("content_hash") != draft_golden[i]["content_hash"]]
    check("all 30 baseline manifest entries still present with unchanged hashes",
          not missing and not changed, f"missing={missing} changed={changed}")

    d = workdir(DATA)
    code, counts, out = manifest_status(d)
    check("live manifest: 0 stale, 0 orphaned, 0 drafts missing",
          code == 0 and counts.get("stale") == 0 and counts.get("orphaned") == 0 and counts.get("missing") == 0, out)
    print(f"     (live decisions: approved={counts.get('approved')} rejected={counts.get('rejected')} "
          f"unreviewed={counts.get('unreviewed')})")

    code, out = build_approved(d)
    check("live approved_train.jsonl equals a fresh rebuild of current data",
          code == 0 and same_bytes(d / "approved.out.jsonl", DATA / "approved_train.jsonl"), out)
    code, out = build_final(d, "approved_train.jsonl")
    check("live final_train.jsonl equals a fresh rebuild of current data",
          code == 0 and same_bytes(d / "final.out.jsonl", DATA / "final_train.jsonl"), out)


# ---------------------------------------------------------------------------
# Checksum helper (used by run_all.py to guard data/)
# ---------------------------------------------------------------------------

def test_checksum_detection():
    print("== Data integrity checksum helper ==")
    d = Path(tempfile.mkdtemp(dir=WORK))
    (d / "sub").mkdir()
    (d / "a.jsonl").write_bytes(b'{"x": 1}\r\n')
    (d / "sub" / "b.json").write_bytes(b"[]")
    base = tree_checksums(d)
    check("unchanged tree -> no differences", diff_checksums(base, tree_checksums(d)) == ([], [], []))

    (d / "a.jsonl").write_bytes(b'{"x": 1}\n')  # line ending only
    check("changed file detected (even a line-ending change)",
          diff_checksums(base, tree_checksums(d))[0] == ["a.jsonl"])
    (d / "a.jsonl").write_bytes(b'{"x": 1}\r\n')

    (d / "sub" / "new.jsonl").write_bytes(b"")
    check("added file detected", diff_checksums(base, tree_checksums(d))[1] == ["sub/new.jsonl"])
    (d / "sub" / "new.jsonl").unlink()

    (d / "sub" / "b.json").unlink()
    check("removed file detected", diff_checksums(base, tree_checksums(d))[2] == ["sub/b.json"])


# ---------------------------------------------------------------------------

def main():
    global WORK
    data_before = tree_checksums(DATA)
    fixtures_before = tree_checksums(FIXTURES)

    with tempfile.TemporaryDirectory(prefix="nirva_golden_") as tmp:
        WORK = tmp
        if test_fixture_integrity():
            golden = rjson(FIXTURES / "golden.json")
            test_golden(golden)
            test_snapshots()
            test_manifest_compatibility(golden)
            test_live(golden)
        test_checksum_detection()

    print("== Files untouched by this test run ==")
    for label, root, before in (("data/", DATA, data_before), ("fixtures", FIXTURES, fixtures_before)):
        changed, added, removed = diff_checksums(before, tree_checksums(root))
        check(f"{label} unchanged", not (changed or added or removed),
              f"changed={changed} added={added} removed={removed}")

    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} tests passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
