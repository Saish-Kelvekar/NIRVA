"""Advisory quality checks for NIRVA datasets (standard library only).

These checks only REPORT. They never modify, remove, merge, approve or
reject anything, and no pipeline script calls them yet. A finding means
"a person should look at this", not "this is wrong".

Every check returns a list of findings:

    {"check": str, "severity": "warning" | "info",
     "ids": [example ids...], "message": str, "data": {...}}

"warning" = needs human review. "info" = context for the reviewer.

Checks:
    exact_duplicates      normalised-identical questions
    near_duplicates       character 3-gram / content-word Jaccard similarity
    unsupported_entities  names or numbers not found in the linked fact text
    answer_distribution   repeated answers, examples per fact, answer lengths
    behaviour_share       behaviour examples as a share of the dataset
    eval_overlap          training questions vs evaluation questions
    traceability          links between examples, facts and manifest entries

Thresholds are PROVISIONAL (see THRESHOLDS). They were calibrated on the
30 baseline drafts only and are not final quality rules.

IDs, hashes and text normalisation come from pipeline_common /
validate_facts, so this module always agrees with the pipeline.
"""

import json
import re
import statistics
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from pipeline_common import content_hash, make_example_id, message_errors
from validate_facts import normalise_text

# ---------------------------------------------------------------------------
# Configuration (provisional)
# ---------------------------------------------------------------------------

THRESHOLDS = {
    # Near-duplicate questions. Character 3-gram Jaccard on lowercased
    # alphanumeric tokens; content-word Jaccard after removing STOPWORDS.
    "same_fact_char": 0.60,
    "same_fact_word": 0.75,
    "cross_fact_char": 0.50,
    # Evaluation overlap uses the cross-fact character threshold and the
    # content-word threshold, because eval questions are not linked to facts.
    "eval_char": 0.50,
    "eval_word": 0.75,
    # Answer distribution.
    "max_identical_answer": 4,       # warn when one answer text is used more often
    "fact_overrepresented_ratio": 2.0,  # warn when a fact has > ratio x median examples
    # Behaviour share target confirmed by the project owner (2026-11-20).
    "behaviour_share_min": 0.12,
    "behaviour_share_max": 0.25,
}

STOPWORDS = frozenset(
    "a an the is are was were of in on to for and or what which where when who how "
    "does do can be by with at from about there any".split()
)

# Places named in the canonical system prompt; every NIRVA answer is about
# them, so mentioning them is never treated as an unsupported entity.
SCOPE_TERMS = ("Dandeli", "Uttara Kannada", "Karnataka", "India")

# Capitalised words that start questions or sentences and are not names.
_NON_ENTITY_WORDS = frozenset(
    "what which where when who whom whose why how is are was were do does did can could "
    "should would will shall may might tell give explain list name describe show find "
    "the a an in on at for to from of and or but if yes no please hi hello hey thanks "
    "according there it its this these that those my our we you your i i'm i've i'd "
    "i'll me let let's any some all also".split()
)

# Words, numbers, and punctuation that ends a name ("A, B and C" are three names).
_TOKEN = re.compile(r"[A-Za-z][A-Za-z0-9'’-]*|\d+(?:[.,]\d+)*|[,;:()\[\]\"/&]")
_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")
_SENTENCE_SPLIT = re.compile(r"(?<=[.?!])\s+")


def finding(check, severity, ids, message, **data):
    return {"check": check, "severity": severity, "ids": list(ids), "message": message, "data": data}


# ---------------------------------------------------------------------------
# Loading (never raises on malformed content; problems become findings)
# ---------------------------------------------------------------------------

def kind_of(source_id):
    return "behaviour" if str(source_id or "").startswith("BEHAVIOUR") else "knowledge"


def load_examples(path):
    """Return (examples, problems) from a JSONL dataset.

    Each example: example_id, id_explicit, source_id, question, answer,
    kind, where. Malformed lines are reported, not raised. A missing file
    raises FileNotFoundError (the caller decides how to report it).
    """
    path = Path(path)
    examples, problems = [], []
    text = path.read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        where = f"{path.name} line {number}"
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            problems.append(finding("input", "warning", [], f"{where}: invalid JSON ({error.msg})", where=where))
            continue
        if not isinstance(record, dict):
            problems.append(finding("input", "warning", [], f"{where}: record is not a JSON object", where=where))
            continue
        errors = message_errors(record)
        if errors:
            problems.append(finding("input", "warning", [], f"{where}: {'; '.join(errors)}", where=where))
            continue
        source_id = record.get("source_fact_id")
        source_id = source_id if isinstance(source_id, str) else ""
        question = record["messages"][1]["content"]
        explicit = record.get("example_id")
        examples.append({
            "example_id": explicit if isinstance(explicit, str) and explicit else make_example_id(source_id, question),
            "id_explicit": isinstance(explicit, str) and bool(explicit),
            "source_id": source_id,
            "question": question,
            "answer": record["messages"][2]["content"],
            "kind": kind_of(source_id),
            "where": where,
        })
    if not examples and not problems:
        problems.append(finding("input", "warning", [], f"{path.name}: contains no examples"))
    return examples, problems


def load_eval_questions(path):
    """Return (questions, problems). Each question: id, category, question."""
    path = Path(path)
    problems = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [], [finding("input", "warning", [], f"{path.name}: invalid JSON ({error.msg})")]
    if not isinstance(data, list):
        return [], [finding("input", "warning", [], f"{path.name}: expected a list of questions")]
    questions = []
    for position, item in enumerate(data, start=1):
        if not isinstance(item, dict) or not isinstance(item.get("question"), str) or not item["question"].strip():
            problems.append(finding("input", "warning", [], f"{path.name} item {position}: missing question text"))
            continue
        questions.append({"id": item.get("id", position), "category": item.get("category", ""),
                          "question": item["question"]})
    return questions, problems


def load_json_or_none(path):
    """Load JSON if the path exists; return (data, problem_or_None)."""
    if path is None or not Path(path).exists():
        return None, None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8")), None
    except json.JSONDecodeError as error:
        return None, finding("input", "warning", [], f"{Path(path).name}: invalid JSON ({error.msg})")


def facts_by_id(facts):
    if not isinstance(facts, list):
        return {}
    return {f["id"]: f for f in facts if isinstance(f, dict) and isinstance(f.get("id"), str)}


def manifest_by_id(manifest):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("examples"), list):
        return {}
    return {e["example_id"]: e for e in manifest["examples"] if isinstance(e, dict) and e.get("example_id")}


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def char_ngrams(text, n=3):
    joined = " ".join(tokens(text))
    return {joined[i:i + n] for i in range(len(joined) - n + 1)}


def content_words(text):
    return {t for t in tokens(text) if t not in STOPWORDS}


def jaccard(a, b):
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def question_similarity(q1, q2):
    """Return (char_3gram_jaccard, content_word_jaccard), rounded to 3 places."""
    return (round(jaccard(char_ngrams(q1), char_ngrams(q2)), 3),
            round(jaccard(content_words(q1), content_words(q2)), 3))


# ---------------------------------------------------------------------------
# 1. Exact duplicates
# ---------------------------------------------------------------------------

def exact_duplicates(examples):
    groups = defaultdict(list)
    for ex in examples:
        groups[normalise_text(ex["question"])].append(ex)
    findings = []
    for key, group in groups.items():
        if len(group) > 1:
            sources = sorted({ex["source_id"] for ex in group})
            findings.append(finding(
                "exact_duplicate", "warning", [ex["example_id"] for ex in group],
                f"{len(group)} examples ask the same normalised question: {group[0]['question']!r}",
                normalised=key, source_ids=sources,
                same_source=len(sources) == 1,
            ))
    return findings


# ---------------------------------------------------------------------------
# 2. Near duplicates
# ---------------------------------------------------------------------------

def near_duplicates(examples, thresholds=THRESHOLDS):
    """Pairs of questions above the provisional similarity thresholds.

    Exact duplicates are skipped here (exact_duplicates reports them).
    """
    findings = []
    for a, b in combinations(examples, 2):
        if normalise_text(a["question"]) == normalise_text(b["question"]):
            continue
        char, word = question_similarity(a["question"], b["question"])
        same = a["source_id"] == b["source_id"]
        rules = []
        if same and char >= thresholds["same_fact_char"]:
            rules.append(f"same-source char >= {thresholds['same_fact_char']}")
        if same and word >= thresholds["same_fact_word"]:
            rules.append(f"same-source content-word >= {thresholds['same_fact_word']}")
        if not same and char >= thresholds["cross_fact_char"]:
            rules.append(f"different-source char >= {thresholds['cross_fact_char']}")
        if rules:
            findings.append(finding(
                "near_duplicate", "warning", [a["example_id"], b["example_id"]],
                f"{'Same' if same else 'Different'}-source questions are similar "
                f"(char {char:.2f}, content-word {word:.2f}): {a['question']!r} / {b['question']!r}",
                char_similarity=char, word_similarity=word, same_source=same, rules=rules,
                source_ids=[a["source_id"], b["source_id"]],
            ))
    findings.sort(key=lambda f: -f["data"]["char_similarity"])
    return findings


# ---------------------------------------------------------------------------
# 3. Unsupported entity indicators
# ---------------------------------------------------------------------------

def extract_entities(text):
    """Heuristic: capitalised word runs and numbers.

    Returns (entities, numbers, sentence_initial) where sentence_initial is
    the set of entities that are a single capitalised word at the start of a
    sentence ("Fees may vary..."): these may be ordinary words, not names.
    Common question/sentence words ("What", "Is", "The"...) are skipped and
    punctuation ends a name. Lowercase names (e.g. animal names) are NOT
    detected; this is a known limitation.
    """
    entities, numbers, sentence_initial = [], [], set()
    for sentence in _SENTENCE_SPLIT.split(text):
        run, run_start, position = [], 0, 0

        def close():
            if run:
                name = " ".join(run)
                entities.append(name)
                if run_start == 0 and len(run) == 1:
                    sentence_initial.add(name)

        for token in _TOKEN.findall(sentence):
            if _NUMBER.fullmatch(token):
                numbers.append(token)
                close()
                run = []
            else:
                word = re.sub(r"['’]s$", "", token)
                if word[:1].isupper() and word.lower() not in _NON_ENTITY_WORDS:
                    if not run:
                        run_start = position
                    run.append(word)
                else:
                    close()
                    run = []
            position += 1
        close()
    # A name used both mid-sentence and sentence-initially is a real name.
    sentence_initial -= {e for e in entities if entities.count(e) > 1}
    return entities, numbers, sentence_initial


def _contains(haystack, entity):
    """Case-insensitive whole-phrase match, tolerating a plural 's'."""
    for form in {entity, entity[:-1] if entity.endswith("s") else entity, entity + "s"}:
        if re.search(r"(?<![a-z0-9])" + re.escape(form.lower()) + r"(?![a-z0-9])", haystack):
            return True
    return False


def unsupported_entities(examples, facts):
    """Flag names/numbers in questions and answers not found in the linked fact.

    Supporting text for a knowledge example = its fact text + the fact's
    publisher name + SCOPE_TERMS. Behaviour examples have no fact, so only
    SCOPE_TERMS support them. Finding no match does not mean the entity is
    false: it may be supported by the source page and simply not appear in
    the recorded fact text.
    """
    facts = facts_by_id(facts)
    findings = []
    for ex in examples:
        fact = facts.get(ex["source_id"])
        if ex["kind"] == "knowledge" and fact is None:
            continue  # traceability reports unknown facts
        support_parts = list(SCOPE_TERMS)
        if fact:
            support_parts += [str(fact.get("fact", "")), str(fact.get("source", ""))]
        support = " ".join(support_parts).lower()
        support_numbers = set(_NUMBER.findall(support))
        for field in ("question", "answer"):
            names, numbers, sentence_initial = extract_entities(ex[field])
            for name in dict.fromkeys(names):
                if _contains(support, name):
                    continue
                words = name.split()
                found = [w for w in words if _contains(support, w)]
                missing = [w for w in words if w not in found]
                where = f"fact {ex['source_id']}" if fact else "the NIRVA scope terms (behaviour example: no fact)"
                if not missing:
                    # Every word is in the fact, just not as this exact phrase.
                    severity = "info"
                    reason = (f"the phrase '{name}' is not in {where}, but each of its words is; "
                              f"likely a rewording")
                elif name in sentence_initial:
                    severity = "info"
                    reason = (f"'{name}' is not in {where}; it is the capitalised first word of a sentence "
                              f"and may be an ordinary word rather than a name")
                else:
                    severity = "warning"
                    reason = f"'{name}' does not appear in {where}"
                    if found:
                        reason += (f"; only part of it does (found {', '.join(repr(w) for w in found)}, "
                                   f"missing {', '.join(repr(w) for w in missing)})")
                findings.append(finding(
                    "unsupported_entity", severity, [ex["example_id"]],
                    f"{field.capitalize()} mentions {name!r}: {reason}. It may still be supported by the "
                    f"source page; check before relying on it.",
                    field=field, entity=name, source_id=ex["source_id"], text=ex[field], missing_words=missing,
                ))
            for value in dict.fromkeys(numbers):
                if value not in support_numbers:
                    findings.append(finding(
                        "unsupported_entity", "warning", [ex["example_id"]],
                        f"{field.capitalize()} contains the number {value!r}, which does not appear in "
                        f"{'fact ' + ex['source_id'] if fact else 'any fact'}.",
                        field=field, entity=value, source_id=ex["source_id"], text=ex[field],
                    ))
    return findings


# ---------------------------------------------------------------------------
# 4. Answer distribution
# ---------------------------------------------------------------------------

def _stats(values):
    if not values:
        return {"count": 0}
    return {"count": len(values), "min": min(values), "median": statistics.median(values),
            "mean": round(statistics.mean(values), 1), "max": max(values)}


def answer_distribution(examples, facts=None, thresholds=THRESHOLDS):
    """Return (summary, findings)."""
    findings = []

    by_answer = defaultdict(list)
    for ex in examples:
        by_answer[ex["answer"].strip()].append(ex)
    repeated = []
    for answer, group in by_answer.items():
        if len(group) > 1:
            entry = {"answer": answer, "count": len(group), "ids": [e["example_id"] for e in group],
                     "source_ids": sorted({e["source_id"] for e in group})}
            repeated.append(entry)
            if len(group) > thresholds["max_identical_answer"]:
                findings.append(finding(
                    "repeated_answer", "warning", entry["ids"],
                    f"The same answer is used {len(group)} times (more than "
                    f"{thresholds['max_identical_answer']}): {answer[:80]!r}",
                    count=len(group)))
            if len(entry["source_ids"]) > 1:
                findings.append(finding(
                    "repeated_answer", "warning", entry["ids"],
                    f"The same answer text is linked to different sources {entry['source_ids']}: {answer[:80]!r}",
                    count=len(group)))
    repeated.sort(key=lambda r: -r["count"])

    knowledge = [ex for ex in examples if ex["kind"] == "knowledge"]
    per_source = Counter(ex["source_id"] for ex in examples)
    knowledge_counts = Counter(ex["source_id"] for ex in knowledge)
    median = statistics.median(knowledge_counts.values()) if knowledge_counts else 0
    limit = thresholds["fact_overrepresented_ratio"] * median
    for source_id, count in sorted(knowledge_counts.items()):
        if median and count > limit:
            findings.append(finding(
                "fact_balance", "warning", [ex["example_id"] for ex in knowledge if ex["source_id"] == source_id],
                f"{source_id} has {count} examples, more than {thresholds['fact_overrepresented_ratio']}x "
                f"the median ({median}).", source_id=source_id, count=count))
        elif median and count < median:
            findings.append(finding(
                "fact_balance", "info", [ex["example_id"] for ex in knowledge if ex["source_id"] == source_id],
                f"{source_id} has {count} example(s), fewer than the median ({median}).",
                source_id=source_id, count=count))

    facts = facts_by_id(facts)
    unrepresented = sorted(fid for fid, f in facts.items()
                           if f.get("status") == "verified" and fid not in knowledge_counts)
    if unrepresented:
        findings.append(finding(
            "fact_balance", "warning", [],
            f"{len(unrepresented)} verified fact(s) have no examples: {', '.join(unrepresented)}.",
            source_ids=unrepresented))

    summary = {
        "repeated_answers": repeated,
        "distinct_answers": len(by_answer),
        "examples_per_source": dict(sorted(per_source.items())),
        "knowledge_median_per_fact": median,
        "verified_facts_without_examples": unrepresented,
        "answer_words": {kind: _stats([len(ex["answer"].split()) for ex in examples if ex["kind"] == kind])
                         for kind in ("knowledge", "behaviour")},
        "answer_chars": {kind: _stats([len(ex["answer"]) for ex in examples if ex["kind"] == kind])
                         for kind in ("knowledge", "behaviour")},
        "question_words": _stats([len(ex["question"].split()) for ex in examples]),
    }
    if examples:
        longest = max(examples, key=lambda ex: len(ex["answer"]))
        shortest = min(examples, key=lambda ex: len(ex["answer"]))
        summary["longest_answer"] = {"id": longest["example_id"], "chars": len(longest["answer"])}
        summary["shortest_answer"] = {"id": shortest["example_id"], "chars": len(shortest["answer"])}
    return summary, findings


BEHAVIOUR_NOT_APPLICABLE = "Not applicable — behaviour examples are not present in this dataset"


def behaviour_share(examples, thresholds=THRESHOLDS, dataset_kind="final"):
    """Return (summary, findings) for the behaviour-example share.

    The 12-25% target describes the final training dataset. It is checked
    when dataset_kind is "final" (where 0 behaviour examples is a real
    problem) or when the input actually contains behaviour examples. For a
    drafts or approved-only file without behaviour examples (behaviour
    examples are added later, by prepare_final_dataset.py) the share is
    "not applicable": no percentage is calculated and nothing is flagged.
    """
    total = len(examples)
    behaviour = sum(1 for ex in examples if ex["kind"] == "behaviour")
    applicable = dataset_kind == "final" or behaviour > 0
    summary = {"total": total, "knowledge": total - behaviour, "behaviour": behaviour,
               "behaviour_share": None, "behaviour_share_applicable": applicable,
               "behaviour_share_note": "" if applicable else BEHAVIOUR_NOT_APPLICABLE}
    if not applicable:
        return summary, [finding("behaviour_share", "info", [], f"{BEHAVIOUR_NOT_APPLICABLE} "
                                 f"(checked as: {dataset_kind}); the {thresholds['behaviour_share_min']:.0%}-"
                                 f"{thresholds['behaviour_share_max']:.0%} target applies to the final dataset.")]
    share = behaviour / total if total else 0.0
    summary["behaviour_share"] = share
    low, high = thresholds["behaviour_share_min"], thresholds["behaviour_share_max"]
    findings = []
    if total and not (low <= share <= high):
        findings.append(finding("behaviour_share", "warning", [],
                                f"Behaviour examples are {share:.0%} of the dataset; target is {low:.0%}-{high:.0%}.",
                                share=share))
    elif total and share - low < 0.02:
        findings.append(finding("behaviour_share", "info", [],
                                f"Behaviour examples are {share:.0%}, at the bottom of the {low:.0%}-{high:.0%} "
                                f"target; adding knowledge examples alone would push it below.", share=share))
    return summary, findings


# ---------------------------------------------------------------------------
# 5. Evaluation overlap
# ---------------------------------------------------------------------------

def eval_overlap(examples, eval_questions, thresholds=THRESHOLDS):
    """Return (rows, findings). One row per eval question with its closest training question."""
    rows, findings = [], []
    for item in eval_questions:
        key = normalise_text(item["question"])
        exact = [ex for ex in examples if normalise_text(ex["question"]) == key]
        best, best_scores = None, (0.0, 0.0)
        for ex in examples:
            scores = question_similarity(item["question"], ex["question"])
            if scores > best_scores:
                best, best_scores = ex, scores
        char, word = best_scores
        status = "exact" if exact else (
            "near" if char >= thresholds["eval_char"] or word >= thresholds["eval_word"] else "none")
        rows.append({"eval_id": item["id"], "category": item["category"], "question": item["question"],
                     "closest_id": best["example_id"] if best else None,
                     "closest_question": best["question"] if best else None,
                     "char_similarity": char, "word_similarity": word, "status": status})
        if exact:
            findings.append(finding("eval_overlap", "warning", [ex["example_id"] for ex in exact],
                                    f"Eval question {item['id']} appears verbatim (normalised) in training: "
                                    f"{item['question']!r}", eval_id=item["id"]))
        elif status == "near":
            findings.append(finding("eval_overlap", "warning", [best["example_id"]],
                                    f"Eval question {item['id']} is close to a training question "
                                    f"(char {char:.2f}, content-word {word:.2f}): {item['question']!r} / "
                                    f"{best['question']!r}", eval_id=item["id"], char_similarity=char,
                                    word_similarity=word))
    return rows, findings


# ---------------------------------------------------------------------------
# 6. Traceability
# ---------------------------------------------------------------------------

def traceability(examples, facts=None, manifest=None, dataset_kind="final"):
    """Check links: example -> source fact -> manifest entry.

    dataset_kind: "drafts" (anything may be unreviewed), "approved" or
    "final" (every knowledge example must be approved and verified).
    facts / manifest may be None, in which case those links are not checked.
    """
    strict = dataset_kind in {"approved", "final"}
    facts_index = facts_by_id(facts) if facts is not None else None
    entries = manifest_by_id(manifest) if manifest is not None else None
    findings = []
    implicit_ids, behaviour_ids = [], []

    for ex in examples:
        eid, sid = ex["example_id"], ex["source_id"]
        if not sid:
            findings.append(finding("traceability", "warning", [eid],
                                    f"{ex['where']}: missing source_fact_id; the example cannot be traced."))
            continue
        if ex["id_explicit"]:
            derived = make_example_id(sid, ex["question"])
            if eid != derived:
                findings.append(finding("traceability", "warning", [eid],
                                        f"{ex['where']}: example_id {eid} does not match its source and question "
                                        f"(expected {derived}).", expected=derived))
        else:
            implicit_ids.append(eid)

        if ex["kind"] == "behaviour":
            behaviour_ids.append(eid)
            continue

        fact = None
        if facts_index is not None:
            fact = facts_index.get(sid)
            if fact is None:
                findings.append(finding("traceability", "warning", [eid],
                                        f"{ex['where']}: source fact {sid} does not exist in the fact file."))
            elif fact.get("status") != "verified":
                findings.append(finding("traceability", "warning" if strict else "info", [eid],
                                        f"{ex['where']}: source fact {sid} has status {fact.get('status')!r}, "
                                        f"not 'verified'."))

        entry = entries.get(eid) if entries is not None else None
        if entries is not None:
            if entry is None:
                findings.append(finding("traceability", "warning", [eid],
                                        f"{ex['where']}: no review manifest entry for {eid}."))
            else:
                if entry.get("content_hash") != content_hash(sid, ex["question"], ex["answer"]):
                    findings.append(finding("traceability", "warning", [eid],
                                            f"{ex['where']}: content differs from the reviewed manifest entry "
                                            f"(content_hash mismatch)."))
                if strict and entry.get("decision") != "approved":
                    findings.append(finding("traceability", "warning", [eid],
                                            f"{ex['where']}: manifest decision is {entry.get('decision')!r}, "
                                            f"but this dataset should contain only approved examples."))

        if fact is not None and ex["answer"].strip() != str(fact.get("fact", "")).strip():
            # Mirrors pipeline_common.answer_check: a reason only covers the
            # exact content it was recorded for (content_hash must match).
            reason = str((entry or {}).get("answer_edit_reason", "")).strip()
            reason_current = bool(reason) and entry.get("content_hash") == content_hash(sid, ex["question"], ex["answer"])
            if reason_current:
                findings.append(finding("traceability", "info", [eid],
                                        f"{ex['where']}: answer differs from {sid} as a recorded reviewed edit.",
                                        reason=reason))
            elif reason:
                findings.append(finding("traceability", "warning", [eid],
                                        f"{ex['where']}: answer differs from {sid}; an answer_edit_reason exists "
                                        f"but was recorded for different content."))
            else:
                findings.append(finding("traceability", "warning", [eid],
                                        f"{ex['where']}: answer differs from the text of {sid} and no "
                                        f"answer_edit_reason is recorded."))

    if implicit_ids:
        findings.append(finding("traceability", "warning" if strict else "info", implicit_ids,
                                f"{len(implicit_ids)} example(s) have no stored example_id; IDs were derived "
                                f"from source and question."))
    if behaviour_ids:
        findings.append(finding("traceability", "info", behaviour_ids,
                                f"{len(behaviour_ids)} behaviour example(s) have no source record or manifest "
                                f"entry (behaviour examples are not yet in the review pipeline)."))

    if entries is not None:
        present = {ex["example_id"] for ex in examples}
        absent = Counter()
        for eid, entry in entries.items():
            if eid in present:
                continue
            fact = facts_index.get(entry.get("source_fact_id")) if facts_index is not None else None
            if not strict:
                findings.append(finding("traceability", "warning", [eid],
                                        f"Manifest entry {eid} has no matching example in this dataset."))
            elif entry.get("decision") != "approved":
                absent[f"decision {entry.get('decision')!r}"] += 1
            elif fact is not None and fact.get("status") != "verified":
                absent[f"fact {entry.get('source_fact_id')} not verified"] += 1
            else:
                findings.append(finding("traceability", "warning", [eid],
                                        f"Manifest entry {eid} is approved with a verified fact but is missing "
                                        f"from this dataset; the dataset may need rebuilding."))
        if absent:
            findings.append(finding("traceability", "info", [],
                                    "Manifest entries not in this dataset, as expected: "
                                    + "; ".join(f"{n} with {why}" for why, n in sorted(absent.items())) + ".",
                                    excluded=dict(absent)))
    return findings
