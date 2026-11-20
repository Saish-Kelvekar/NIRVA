"""Tests for the advisory quality checks (quality_checks.py, dataset_report.py).

Uses synthetic records written to temporary directories ("Foo Lake",
"Bar Hills" ...), plus read-only regression checks on the frozen Stage 0
baseline fixtures. Nothing is added to any training file and nothing in
data/ is written.

Usage (from the project root):
    ai/.venv/Scripts/python.exe ai/training/tests/test_quality_checks.py

Exit status: 0 when all tests pass, 1 otherwise.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
TRAIN = TESTS.parent
ROOT = TRAIN.parents[1]
DATA = ROOT / "data"
FIXTURES = TESTS / "fixtures" / "baseline_2026-11-20"
PY = sys.executable

sys.dont_write_bytecode = True
sys.path.insert(0, str(TRAIN))
sys.path.insert(0, str(TESTS))
import quality_checks as qc  # noqa: E402
from pipeline_common import CANONICAL_SYSTEM_PROMPT, content_hash, make_example_id  # noqa: E402
from test_golden import diff_checksums, tree_checksums  # noqa: E402

results = []
WORK = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)
    if not cond and detail:
        print("     " + str(detail).encode("ascii", "backslashreplace").decode())


def tmpdir():
    return Path(tempfile.mkdtemp(dir=WORK))


def rec(source_id, question, answer, example_id=None):
    record = {"messages": [{"role": "system", "content": CANONICAL_SYSTEM_PROMPT},
                           {"role": "user", "content": question},
                           {"role": "assistant", "content": answer}],
              "source_fact_id": source_id}
    if example_id is not None:
        record["example_id"] = example_id
    return record


def write_jsonl(path, records, raw_lines=()):
    lines = [json.dumps(r, ensure_ascii=False) for r in records] + list(raw_lines)
    Path(path).write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return path


def examples_from(records):
    d = tmpdir()
    examples, problems = qc.load_examples(write_jsonl(d / "set.jsonl", records))
    assert not problems, problems
    return examples


def fact(fid, text, status="verified", source="Example Tourism Board"):
    return {"id": fid, "category": "attractions", "fact": text, "source": source,
            "source_url": "https://example.org/", "confidence": "high", "time_sensitive": False, "status": status}


def of(findings, check_name, severity=None):
    return [f for f in findings if f["check"] == check_name and (severity is None or f["severity"] == severity)]


def report(*args):
    p = subprocess.run([PY, "-B", str(TRAIN / "dataset_report.py"), *map(str, args)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout + p.stderr


FACTS = [fact("FACT901", "Foo Lake is a natural lake in the Bar Hills."),
         fact("FACT902", "Kayaking is offered on Foo Lake."),
         fact("FACT903", "Foo Fort was built in 1850.", status="needs_review"),
         fact("FACT904", "Baz Caves are known for stalagmites.")]


# ---------------------------------------------------------------------------
# Similarity and duplicates
# ---------------------------------------------------------------------------

def test_similarity():
    print("== Similarity ==")
    check("identical questions score 1.0 / 1.0", qc.question_similarity("Where is Foo Lake?", "where is foo lake") == (1.0, 1.0))
    check("empty strings score 0 without error", qc.question_similarity("", "") == (0.0, 0.0))
    check("unrelated questions score near 0",
          max(qc.question_similarity("What birds live at Foo Lake?", "When did Bar Fort open to visitors?")) < 0.1)


def test_exact_duplicates():
    print("== Exact duplicates ==")
    ex = examples_from([
        rec("FACT901", "Where is Foo Lake?", "Foo Lake is a natural lake in the Bar Hills."),
        rec("FACT901", "  where IS foo lake ", "Foo Lake is a natural lake in the Bar Hills."),
        rec("FACT902", "WHERE is Foo Lake?!", "Kayaking is offered on Foo Lake."),
        rec("FACT904", "What are Baz Caves known for?", "Baz Caves are known for stalagmites."),
    ])
    found = qc.exact_duplicates(ex)
    check("normalised duplicates found as one group of 3", len(found) == 1 and len(found[0]["ids"]) == 3, found)
    check("duplicate finding reports both source facts",
          found and found[0]["data"]["source_ids"] == ["FACT901", "FACT902"] and not found[0]["data"]["same_source"])
    check("distinct question not reported", not any(ex[3]["example_id"] in f["ids"] for f in found))
    check("exact duplicates are not repeated as near-duplicates", not qc.near_duplicates(ex[:3]))


def test_near_duplicates():
    print("== Near duplicates ==")
    same_char = examples_from([rec("FACT901", "What can tourists do near Foo Lake?", "a"),
                               rec("FACT901", "What can tourists see near Foo Lake?", "b")])
    found = qc.near_duplicates(same_char)
    check("same-source pair above char threshold flagged with scores and IDs",
          len(found) == 1 and found[0]["data"]["same_source"] and found[0]["data"]["char_similarity"] >= 0.60
          and set(found[0]["ids"]) == {e["example_id"] for e in same_char}, found)

    word_only = examples_from([rec("FACT901", "Birds Foo Lake", "a"),
                               rec("FACT901", "Which birds are there in Foo Lake, and where?", "b")])
    char, word = qc.question_similarity(word_only[0]["question"], word_only[1]["question"])
    found = qc.near_duplicates(word_only)
    check("same-source pair caught by content-word rule alone (char < 0.60, word >= 0.75)",
          char < 0.60 and word >= 0.75 and len(found) == 1
          and any("content-word" in r for r in found[0]["data"]["rules"]), (char, word, found))

    cross = examples_from([rec("FACT902", "Which river flows through Foo Park?", "a"),
                           rec("FACT904", "Which river flows past Foo Park?", "b")])
    found = qc.near_duplicates(cross)
    check("similar questions for DIFFERENT facts flagged (char >= 0.50)",
          len(found) == 1 and not found[0]["data"]["same_source"]
          and found[0]["data"]["source_ids"] == ["FACT902", "FACT904"], found)

    below = examples_from([rec("FACT901", "Which river flows through Foo Park?", "a"),
                           rec("FACT901", "Which river is in Foo Park?", "b")])
    check("same-source pair below both thresholds not flagged", not qc.near_duplicates(below))
    unrelated = examples_from([rec("FACT901", "Where is Foo Lake?", "a"), rec("FACT904", "What animals live in Bar Hills?", "b")])
    check("unrelated different-source pair not flagged", not qc.near_duplicates(unrelated))

    strict = dict(qc.THRESHOLDS, same_fact_char=0.99, same_fact_word=0.99)
    check("thresholds are configurable (raised threshold suppresses the flag)",
          not qc.near_duplicates(same_char, strict))


# ---------------------------------------------------------------------------
# Unsupported entities
# ---------------------------------------------------------------------------

def test_unsupported_entities():
    print("== Unsupported entity indicators ==")
    ex = examples_from([
        rec("FACT901", "Is Foo Lake part of Qux National Park?", "Foo Lake is a natural lake in the Bar Hills."),
        rec("FACT901", "Where is Foo Lake?", "Foo Lake is a natural lake in the Bar Hills."),
        rec("FACT902", "Was Foo Lake formed in 1999?", "Kayaking is offered on Foo Lake."),
        rec("FACT901", "Is the Bar Lake natural?", "Foo Lake is a natural lake in the Bar Hills."),
        rec("BEHAVIOUR901", "Who runs boat trips in Dandeli?", "Please contact Acme River Tours directly."),
        rec("BEHAVIOUR902", "Can I swim?", "Swimming rules vary. Please check locally in Dandeli."),
        rec("FACT999", "Where is Zed Peak?", "Somewhere."),
    ])
    found = qc.unsupported_entities(ex, FACTS)
    by_id = lambda i: [f for f in found if f["ids"] == [ex[i]["example_id"]]]  # noqa: E731

    f0 = by_id(0)
    check("question naming an entity absent from its fact -> warning",
          len(f0) == 1 and f0[0]["severity"] == "warning" and f0[0]["data"]["entity"] == "Qux National Park", f0)
    check("warning explains why and does not call the entity false",
          f0 and "does not appear in fact FACT901" in f0[0]["message"] and "may still be supported" in f0[0]["message"])
    check("supported question and answer -> no finding", not by_id(1))
    f2 = by_id(2)
    check("number absent from the fact -> warning", any(f["data"]["entity"] == "1999" and f["severity"] == "warning" for f in f2), f2)
    f3 = by_id(3)
    check("phrase whose words are all in the fact (reworded) -> info, not warning",
          len(f3) == 1 and f3[0]["severity"] == "info" and "each of its words" in f3[0]["message"], f3)
    f4 = by_id(4)
    check("behaviour answer naming a business -> warning (checked against scope terms)",
          any(f["data"]["entity"] == "Acme River Tours" and f["severity"] == "warning" for f in f4), f4)
    f5 = by_id(5)
    check("capitalised first word of a sentence -> info only",
          all(f["severity"] == "info" for f in f5) and any(f["data"]["entity"] == "Swimming" for f in f5), f5)
    check("unknown fact is left to traceability (no entity finding)", not by_id(6))

    names, numbers, initial = qc.extract_entities("Wildlife includes Malabar Pied Hornbill, Great Hornbill and Hubli.")
    check("commas end a name (lists split into separate entities)",
          names == ["Wildlife", "Malabar Pied Hornbill", "Great Hornbill", "Hubli"] and initial == {"Wildlife"}, names)
    names, numbers, initial = qc.extract_entities("I'm visiting Anshi National Park in 2027. What about Foo?")
    check("question words and I'm are not entities; numbers extracted",
          names == ["Anshi National Park", "Foo"] and numbers == ["2027"], (names, numbers))

    # Regression on the frozen baseline drafts: exactly the two rejected
    # drafts get warnings, and none of the approved ones.
    drafts, _ = qc.load_examples(FIXTURES / "generated_drafts.jsonl")
    facts = json.loads((FIXTURES / "raw_facts.json").read_text(encoding="utf-8"))
    warned = {f["ids"][0] for f in qc.unsupported_entities(drafts, facts) if f["severity"] == "warning"}
    check("baseline drafts: warnings exactly for the 2 rejected 'Kali Tiger Reserve' drafts",
          warned == {"FACT009-9606af01", "FACT010-a4b9ebb6"}, warned)
    approved = {json.loads(l)["example_id"] for l in (FIXTURES / "approved_train.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    check("baseline: no entity warning on any of the 22 approved examples", not (warned & approved))


# ---------------------------------------------------------------------------
# Answer distribution and behaviour share
# ---------------------------------------------------------------------------

def test_answer_distribution():
    print("== Answer distribution ==")
    same = "Kayaking is offered on Foo Lake."
    records = [rec("FACT902", f"Kayaking question {i}?", same) for i in range(6)]
    records += [rec("FACT901", "Where is Foo Lake?", "Foo Lake is a natural lake in the Bar Hills."),
                rec("FACT901", "Is Foo Lake natural?", "Foo Lake is a natural lake in the Bar Hills."),
                rec("FACT904", "What are Baz Caves known for?", "Short answer here."),
                rec("FACT904", "Tell me about Baz Caves.", same),
                rec("BEHAVIOUR901", "Price?", "I do not have verified prices.")]
    summary, found = qc.answer_distribution(examples_from(records), FACTS)

    top = summary["repeated_answers"][0]
    check("repeated identical answers counted (7x)", top["answer"] == same and top["count"] == 7, top)
    check("answer used more than the limit -> warning",
          any(f["check"] == "repeated_answer" and f["data"]["count"] == 7 and "more than 4" in f["message"] for f in found))
    check("same answer text under different facts -> warning",
          any(f["check"] == "repeated_answer" and "different sources" in f["message"] for f in found))
    check("answer used twice is listed but not a warning",
          any(r["count"] == 2 for r in summary["repeated_answers"])
          and not any("more than" in f["message"] and f["data"]["count"] == 2 for f in found))
    check("examples counted per source",
          summary["examples_per_source"] == {"BEHAVIOUR901": 1, "FACT901": 2, "FACT902": 6, "FACT904": 2})
    check("over-represented fact -> warning (6 > 2 x median 2)",
          any(f["check"] == "fact_balance" and f["severity"] == "warning" and f["data"].get("source_id") == "FACT902" for f in found))
    check("every verified fact represented -> none listed as missing",
          summary["verified_facts_without_examples"] == [])
    summary2, found2 = qc.answer_distribution(examples_from(records[:6]), FACTS)
    check("verified facts without examples listed (FACT901, FACT904; not needs_review FACT903)",
          summary2["verified_facts_without_examples"] == ["FACT901", "FACT904"]
          and any("no examples" in f["message"] for f in found2), summary2["verified_facts_without_examples"])

    lengths = examples_from([rec("FACT901", "q1?", "one two"), rec("FACT901", "q2?", "one two three four"),
                             rec("FACT901", "q3?", "one two three four five six")])
    s, _ = qc.answer_distribution(lengths)
    check("answer-length statistics (words): min 2, median 4, mean 4, max 6",
          s["answer_words"]["knowledge"] == {"count": 3, "min": 2, "median": 4, "mean": 4.0, "max": 6},
          s["answer_words"])
    check("answer-length statistics (chars) and longest/shortest reported",
          s["answer_chars"]["knowledge"]["max"] == len("one two three four five six")
          and s["shortest_answer"]["chars"] == 7)
    check("empty example list handled", qc.answer_distribution([])[0]["answer_words"]["knowledge"] == {"count": 0})


def test_behaviour_share():
    print("== Behaviour share ==")
    k = [rec("FACT901", f"Q{i}?", "a") for i in range(9)]
    _, low = qc.behaviour_share(examples_from(k + [rec("BEHAVIOUR901", "B?", "b")]))
    check("10% behaviour -> warning (target 12-25%)", low and low[0]["severity"] == "warning")
    k8 = [rec("FACT901", f"Q{i}?", "a") for i in range(8)]
    s, ok = qc.behaviour_share(examples_from(k8 + [rec("BEHAVIOUR901", "B?", "b"), rec("BEHAVIOUR902", "C?", "c")]))
    check("20% behaviour -> no finding; counts correct", not ok and s["knowledge"] == 8 and s["behaviour"] == 2)
    check("empty final dataset -> share 0, no finding",
          qc.behaviour_share([]) == ({"total": 0, "knowledge": 0, "behaviour": 0, "behaviour_share": 0.0,
                                      "behaviour_share_applicable": True, "behaviour_share_note": ""}, []))

    print("== Behaviour share: dataset-aware ==")
    knowledge_only = examples_from([rec("FACT901", f"Q{i}?", "a") for i in range(5)])
    for kind in ("drafts", "approved"):
        s, found = qc.behaviour_share(knowledge_only, dataset_kind=kind)
        check(f"{kind} without behaviour examples -> not applicable, no percentage",
              s["behaviour_share_applicable"] is False and s["behaviour_share"] is None
              and s["behaviour_share_note"] == qc.BEHAVIOUR_NOT_APPLICABLE
              and s["behaviour_share_note"].startswith("Not applicable")
              and "behaviour examples are not present in this dataset" in s["behaviour_share_note"], s)
        check(f"{kind} without behaviour examples -> no warning, one info note",
              len(found) == 1 and found[0]["severity"] == "info" and "Not applicable" in found[0]["message"], found)
    s, found = qc.behaviour_share(knowledge_only, dataset_kind="final")
    check("final without behaviour examples -> still checked: 0% warning",
          s["behaviour_share_applicable"] and s["behaviour_share"] == 0.0
          and len(found) == 1 and found[0]["severity"] == "warning" and "0%" in found[0]["message"], found)
    mixed = examples_from([rec("FACT901", f"Q{i}?", "a") for i in range(9)] + [rec("BEHAVIOUR901", "B?", "b")])
    s, found = qc.behaviour_share(mixed, dataset_kind="drafts")
    check("drafts that DO contain behaviour examples -> share calculated (10% warning)",
          s["behaviour_share_applicable"] and s["behaviour_share"] == 0.1 and found and found[0]["severity"] == "warning")
    s, found = qc.behaviour_share(examples_from([rec("FACT901", f"Q{i}?", "a") for i in range(22)]
                                                + [rec(f"BEHAVIOUR90{i}", f"B{i}?", "b") for i in range(3)]))
    check("final 3 of 25 -> 12%, in target, info only (bottom of range)",
          abs(s["behaviour_share"] - 0.12) < 1e-9 and found and all(f["severity"] == "info" for f in found), (s, found))
    check("12-25% target unchanged",
          (qc.THRESHOLDS["behaviour_share_min"], qc.THRESHOLDS["behaviour_share_max"]) == (0.12, 0.25))


# ---------------------------------------------------------------------------
# Evaluation overlap
# ---------------------------------------------------------------------------

def test_eval_overlap():
    print("== Evaluation overlap ==")
    ex = examples_from([rec("FACT901", "Where is Foo Lake?", "a"),
                        rec("FACT904", "What can tourists do near Baz Caves?", "b"),
                        rec("BEHAVIOUR901", "Explain quantum physics.", "c")])
    evals = [{"id": 1, "category": "tourism", "question": "WHERE is foo lake"},
             {"id": 2, "category": "tourism", "question": "What can tourists see near Baz Caves?"},
             {"id": 3, "category": "local", "question": "Which festival happens in Bar Hills in winter?"}]
    rows, found = qc.eval_overlap(ex, evals)
    status = {r["eval_id"]: r["status"] for r in rows}
    check("exact (normalised) overlap -> warning", status[1] == "exact"
          and any(f["data"]["eval_id"] == 1 and "verbatim" in f["message"] for f in found), rows)
    check("near overlap -> warning with scores", status[2] == "near"
          and any(f["data"].get("eval_id") == 2 and f["data"]["char_similarity"] >= 0.5 for f in found))
    check("unrelated eval question -> no finding, closest match still shown",
          status[3] == "none" and rows[2]["closest_id"] is not None and not any(f["data"]["eval_id"] == 3 for f in found))
    check("no eval questions -> no rows, no findings", qc.eval_overlap(ex, []) == ([], []))


# ---------------------------------------------------------------------------
# Traceability
# ---------------------------------------------------------------------------

def test_traceability():
    print("== Traceability ==")
    good_q, good_a = "Where is Foo Lake?", "Foo Lake is a natural lake in the Bar Hills."
    good_id = make_example_id("FACT901", good_q)
    records = [
        rec("FACT901", good_q, good_a, good_id),                                    # 0 fine
        {"messages": rec("x", "No source?", "a")["messages"]},                       # 1 no source
        rec("FACT999", "Unknown fact?", "a"),                                        # 2 unknown fact
        rec("FACT902", "Kayaking where?", "Kayaking is offered on Foo Lake.", "FACT902-deadbeef"),  # 3 bad id
        rec("FACT902", "Kayaking on Foo Lake?", "Kayaking is offered on Foo Lake."),  # 4 no manifest entry
        rec("FACT904", "What are Baz Caves known for?", "Baz Caves have stalagmites."),  # 5 hash mismatch + edit reason
        rec("FACT903", "When was Foo Fort built?", "Foo Fort was built in 1850."),   # 6 fact needs_review
        rec("FACT901", "Is Foo Lake natural?", "Yes, it is natural."),               # 7 answer differs, no reason, rejected
        rec("BEHAVIOUR901", "Price?", "I do not have verified prices."),             # 8 behaviour
        rec("FACT904", "Tell me about Baz Caves.", "Baz Caves have stalagmites."),   # 9 reviewed edit, hash current
    ]
    ex = examples_from(records)
    ids = [e["example_id"] for e in ex]
    entry = lambda i, decision="approved", h=None, **kw: dict({  # noqa: E731
        "example_id": ids[i], "source_fact_id": ex[i]["source_id"], "decision": decision,
        "reviewer": "T", "reviewed_on": "2026-11-20",
        "content_hash": h or content_hash(ex[i]["source_id"], ex[i]["question"], ex[i]["answer"])}, **kw)
    manifest = {"examples": [
        entry(0), entry(2), entry(3),
        entry(5, h="0" * 16, answer_edit_reason="Shortened wording."),
        entry(6), entry(7, decision="rejected"), entry(9, answer_edit_reason="Shortened wording."),
        {"example_id": "FACT901-00000000", "source_fact_id": "FACT901", "decision": "approved",
         "reviewer": "T", "reviewed_on": "2026-11-20", "content_hash": "x"},       # approved but absent
        {"example_id": "FACT903-11111111", "source_fact_id": "FACT903", "decision": "approved",
         "reviewer": "T", "reviewed_on": "2026-11-20", "content_hash": "x"},       # absent, fact unverified
    ]}

    final = qc.traceability(ex, FACTS, manifest, "final")
    about = lambda i, fs=final: [f for f in fs if ids[i] in f["ids"] and len(f["ids"]) == 1]  # noqa: E731
    msgs = lambda i, fs=final: " | ".join(f"{f['severity']}:{f['message']}" for f in about(i, fs))  # noqa: E731

    check("fully linked example -> no finding", not about(0), msgs(0))
    check("missing source_fact_id -> warning", any("missing source_fact_id" in f["message"] and f["severity"] == "warning" for f in about(1)), msgs(1))
    check("unknown source fact -> warning", any("does not exist" in f["message"] for f in about(2)), msgs(2))
    check("stored example_id not matching content -> warning", any("does not match" in f["message"] for f in about(3)), msgs(3))
    check("no manifest entry -> warning", any("no review manifest entry" in f["message"] for f in about(4)), msgs(4))
    check("content changed since review -> warning", any("content_hash mismatch" in f["message"] for f in about(5)), msgs(5))
    check("edit reason recorded for different content (stale hash) -> warning, not accepted",
          any(f["severity"] == "warning" and "recorded for different content" in f["message"] for f in about(5))
          and not any("reviewed edit" in f["message"] for f in about(5)), msgs(5))
    check("answer differing from fact with a current recorded reason -> info only",
          about(9) and all(f["severity"] == "info" for f in about(9))
          and any("reviewed edit" in f["message"] for f in about(9)), msgs(9))
    check("final: unverified fact -> warning", any(f["severity"] == "warning" and "not 'verified'" in f["message"] for f in about(6)), msgs(6))
    check("final: rejected decision -> warning", any("decision is 'rejected'" in f["message"] for f in about(7)), msgs(7))
    check("answer differing from fact without reason -> warning",
          any(f["severity"] == "warning" and "no answer_edit_reason" in f["message"] for f in about(7)), msgs(7))
    check("behaviour example -> info only (no fact or manifest warning of its own)",
          any(ids[8] in f["ids"] and f["severity"] == "info" and "not yet in the review pipeline" in f["message"]
              for f in final) and not any(f["severity"] == "warning" for f in about(8)), msgs(8))
    check("final: missing stored example_ids -> warning",
          any(f["severity"] == "warning" and "no stored example_id" in f["message"] for f in final))
    check("final: approved+verified manifest entry missing from dataset -> warning",
          any("FACT901-00000000" in f["ids"] and "may need rebuilding" in f["message"] for f in final))
    check("final: absent entry with unverified fact -> expected (info)",
          any(f["severity"] == "info" and "fact FACT903 not verified" in f["message"] for f in final))

    drafts = qc.traceability(ex, FACTS, manifest, "drafts")
    check("drafts: unverified fact is info, not warning",
          any(f["severity"] == "info" and "not 'verified'" in f["message"] for f in about(6, drafts))
          and not any(f["severity"] == "warning" and "not 'verified'" in f["message"] for f in about(6, drafts)))
    check("drafts: rejected decision is not a warning", not any("decision is" in f["message"] for f in drafts))
    check("drafts: manifest entry with no matching example -> warning",
          any("FACT903-11111111" in f["ids"] and "no matching example" in f["message"] for f in drafts))

    none = qc.traceability(ex, None, None, "final")
    link_checks = ("no review manifest entry", "content_hash", "decision is", "fact file", "not 'verified'",
                   "answer_edit_reason", "Manifest entr")
    check("without facts or manifest those links are skipped (no crash)",
          not any(k in f["message"] for f in none for k in link_checks)
          and any("missing source_fact_id" in f["message"] for f in none),
          [f["message"] for f in none])


# ---------------------------------------------------------------------------
# Malformed and empty input
# ---------------------------------------------------------------------------

def test_malformed_input():
    print("== Malformed and empty input ==")
    d = tmpdir()
    path = write_jsonl(d / "bad.jsonl", [rec("FACT901", "Where is Foo Lake?", "Foo Lake is a natural lake in the Bar Hills.")],
                       raw_lines=["{not json", "[1, 2]", "", '{"messages": [{"role": "user", "content": "x"}]}',
                                  json.dumps(rec("FACT901", "  ", "a")),
                                  json.dumps({"messages": [{"role": "system", "content": "s"}, {"role": "assistant", "content": "a"},
                                                           {"role": "user", "content": "q"}]})])
    ex, problems = qc.load_examples(path)
    text = " | ".join(p["message"] for p in problems)
    check("valid line kept; 5 malformed lines reported (blank line ignored)", len(ex) == 1 and len(problems) == 5, text)
    check("problems name the line and the reason",
          "line 2: invalid JSON" in text and "line 3: record is not a JSON object" in text
          and "exactly 3 messages" in text and "empty user message" in text and "roles must be" in text, text)

    (d / "empty.jsonl").write_text("", encoding="utf-8")
    ex, problems = qc.load_examples(d / "empty.jsonl")
    check("empty file -> no examples, one warning", ex == [] and len(problems) == 1 and "no examples" in problems[0]["message"])

    for content, expect in (("{bad", "invalid JSON"), ('{"a": 1}', "expected a list"),
                            ('[{"id": 1}, {"id": 2, "question": "Where is Foo Lake?"}, "x"]', "missing question")):
        (d / "eval.json").write_text(content, encoding="utf-8")
        qs, problems = qc.load_eval_questions(d / "eval.json")
        check(f"malformed eval file reported ({expect})", problems and expect in problems[0]["message"], problems)
    check("partially valid eval file keeps the valid question", len(qs) == 1 and len(problems) == 2)

    (d / "facts.json").write_text("[{", encoding="utf-8")
    data, problem = qc.load_json_or_none(d / "facts.json")
    check("invalid facts JSON -> reported, not raised", data is None and "invalid JSON" in problem["message"])
    check("missing optional file -> (None, None)", qc.load_json_or_none(d / "nope.json") == (None, None))
    check("non-list facts / non-dict manifest tolerated", qc.facts_by_id({"x": 1}) == {} and qc.manifest_by_id([1]) == {})


# ---------------------------------------------------------------------------
# dataset_report.py (CLI)
# ---------------------------------------------------------------------------

def test_report_cli():
    print("== dataset_report.py ==")
    d = tmpdir()
    write_jsonl(d / "final_train.jsonl", [rec("FACT901", "Where is Foo Lake?", "Foo Lake is a natural lake in the Bar Hills."),
                                           rec("FACT901", "where is foo lake", "Foo Lake is a natural lake in the Bar Hills."),
                                           rec("BEHAVIOUR901", "Price?", "I do not have verified prices.")],
                raw_lines=["{broken"])
    (d / "facts.json").write_text(json.dumps(FACTS), encoding="utf-8")
    (d / "eval.json").write_text(json.dumps([{"id": 1, "category": "tourism", "question": "Where is Foo Lake?"}]),
                                 encoding="utf-8")
    base = ["--dataset", d / "final_train.jsonl", "--facts", d / "facts.json",
            "--manifest", d / "no_manifest.json", "--eval", d / "eval.json"]
    before = tree_checksums(d)
    code, out = report(*base)
    check("report runs on malformed input and exits 0", code == 0, out[-2000:])
    for heading in ("1. SUMMARY", "2. EXAMPLES PER SOURCE", "3. ANSWER DISTRIBUTION", "4. EVALUATION OVERLAP",
                    "5. FINDINGS BY CHECK", "6. WARNINGS REQUIRING HUMAN REVIEW"):
        check(f"report has section '{heading}'", heading in out)
    check("report shows knowledge/behaviour counts and percentages",
          "Total examples:     3" in out and "Knowledge:          2 (67%)" in out and "Behaviour:          1 (33%)" in out, out[:1500])
    check("report lists the exact duplicate, eval overlap and input problem",
          "same normalised question" in out and "[EXACT]" in out and "invalid JSON" in out)
    check("missing manifest is reported as not loaded", "manifest loaded: False" in out)
    check("report without --json writes nothing", diff_checksums(before, tree_checksums(d)) == ([], [], []))

    code, out = report(*base, "--json", d / "r.json")
    data = json.loads((d / "r.json").read_text(encoding="utf-8")) if (d / "r.json").exists() else {}
    check("--json writes a machine-readable report", code == 0 and data.get("summary", {}).get("total") == 3
          and isinstance(data.get("findings"), list))
    stamp = (d / "r.json").read_bytes()
    code, out = report(*base, "--json", d / "r.json")
    check("--json refuses to overwrite an existing file", code == 2 and "Refusing" in out and (d / "r.json").read_bytes() == stamp)

    code, out = report("--dataset", d / "missing.jsonl")
    check("missing dataset -> exit 2", code == 2 and "not found" in out)

    code, out = report("--dataset", FIXTURES / "generated_drafts.jsonl", "--facts", FIXTURES / "raw_facts.json",
                       "--manifest", FIXTURES / "review_manifest.json", "--eval", d / "eval.json",
                       "--json", d / "drafts.json")
    check("kind inferred from file name (drafts)", "(checked as: drafts)" in out, out[:400])
    dr = json.loads((d / "drafts.json").read_text(encoding="utf-8"))
    check("baseline drafts report: behaviour share 'Not applicable', no percentage shown",
          "Behaviour share:    Not applicable" in out and "behaviour examples are not present in this dataset" in out
          and "Behaviour:          0 (0%)" not in out, out[:1200])
    check("'Not applicable' wording survives piped output intact (UTF-8 em dash)",
          "Not applicable — behaviour examples are not present in this dataset" in out and "�" not in out)
    check("baseline drafts report: no behaviour-share warning; share is null in JSON",
          not of(dr["findings"], "behaviour_share", "warning") and dr["summary"]["behaviour_share"] is None
          and dr["summary"]["behaviour_share_applicable"] is False)

    # Frozen baseline final dataset: known findings.
    code, out = report("--dataset", FIXTURES / "final_train.jsonl", "--facts", FIXTURES / "raw_facts.json",
                       "--manifest", FIXTURES / "review_manifest.json", "--eval", d / "eval.json", "--json", d / "base.json")
    b = json.loads((d / "base.json").read_text(encoding="utf-8"))
    warn = [f for f in b["findings"] if f["severity"] == "warning"]
    check("baseline final: 25 examples, 22 knowledge, 3 behaviour",
          (b["summary"]["total"], b["summary"]["knowledge"], b["summary"]["behaviour"]) == (25, 22, 3))
    check("baseline final: behaviour share calculated (12%) against the 12-25% target",
          b["summary"]["behaviour_share_applicable"] and abs(b["summary"]["behaviour_share"] - 0.12) < 1e-9
          and "Behaviour:          3 (12%)   target 12%-25%" in out and "Not applicable" not in out
          and not of(b["findings"], "behaviour_share", "warning"))
    check("baseline final: no exact duplicates, no traceability or entity warnings",
          not of(b["findings"], "exact_duplicate") and not of(warn, "traceability") and not of(warn, "unsupported_entity"))
    near = of(b["findings"], "near_duplicate")
    check("baseline final: only near-duplicate is the FACT006 pair",
          len(near) == 1 and set(near[0]["ids"]) == {"FACT006-41f44fa1", "FACT006-db5ee384"}, near)
    check("baseline final: FACT016-FACT019 reported as verified facts with no examples",
          b["distribution"]["verified_facts_without_examples"] == ["FACT016", "FACT017", "FACT018", "FACT019"])

    code, out = report()
    check("default run on live data exits 0", code == 0 and "1. SUMMARY" in out, out[-1500:])


# ---------------------------------------------------------------------------

def main():
    global WORK
    data_before = tree_checksums(DATA)
    with tempfile.TemporaryDirectory(prefix="nirva_qc_") as tmp:
        WORK = tmp
        test_similarity()
        test_exact_duplicates()
        test_near_duplicates()
        test_unsupported_entities()
        test_answer_distribution()
        test_behaviour_share()
        test_eval_overlap()
        test_traceability()
        test_malformed_input()
        test_report_cli()
    changed, added, removed = diff_checksums(data_before, tree_checksums(DATA))
    check("data/ unchanged by this test run", not (changed or added or removed), (changed, added, removed))
    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} tests passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
