# NIRVA Knowledge Base — Sources, Fact Rules and Workflow

This file is the reference for how NIRVA facts are sourced, verified,
turned into training drafts, reviewed and approved.

## 1. Source inventory

All current facts come from two official publishers. Every page below was
read on 2026-11-19 and returned its full text. S1, S2 and S5 were read again
on 2026-11-20 for the Day 2 source audit (section 10).

### Canonical source pages

| # | Publisher | Page | Canonical URL | Cited by |
|---|-----------|------|---------------|----------|
| S1 | Uttara Kannada District Administration | Dandeli Wildlife Sanctuary | https://uttarakannada.nic.in/en/tourist-place/dandeli-wildlife-sanctuary/ | FACT001, FACT006, FACT014, FACT018, FACT021, FACT022 |
| S2 | Karnataka Tourism | Dandeli Wildlife Sanctuary | https://karnatakatourism.org/en/experiences/dandeli-wildlife-sanctuary | FACT002, FACT004, FACT005, FACT011, FACT016, FACT019, FACT020, FACT025 |
| S3 | Karnataka Tourism | Kali Tiger Reserve | https://karnatakatourism.org/en/experiences/kali-tiger-reserve/ | FACT003, FACT007, FACT008, FACT010 |
| S4 | Karnataka Tourism | Hornbills of Dandeli | https://karnatakatourism.org/en/experiences/hornbills-of-dandeli/ | FACT009 |
| S5 | Karnataka Tourism | Rafting in Dandeli | https://karnatakatourism.org/en/experiences/rafting-in-dandeli/ | FACT012, FACT013 (rejected, superseded), FACT017, FACT026 |
| S6 | Karnataka Tourism | Kayaking in Dandeli | https://karnatakatourism.org/en/experiences/kayaking-in-dandeli/ | FACT015 |

### Evaluated and not registered

| Site | Evaluated | Reason not registered |
|------|-----------|-----------------------|
| https://kalitigerreserve.org | 2026-11-20 (Day 2 audit, proposed as "S7") | Official provenance not verified. The visible text never says the site is an official or Karnataka Forest Department website. It has no `.gov.in` / `.nic.in` link or government emblem, and its footer reads "© Kali Tiger Reserve, All Rights Reserved \| Digital Partner - Tecobytes". It sells stays ("Starts just at ₹ 550/-") with booking on kalitigerreserve.store. Do not cite it unless an official government page confirms it as the reserve's site. |
| https://www.junglelodges.com/resort/kali-adventure-camp/ | Not evaluated | Proposed as "S8" by the audit, but it was outside the approved Day 2 scope. |

### Duplicate pages (do not cite)

Karnataka Tourism publishes the same content under both `/en/experiences/`
and `/en/attractions/`. The `/experiences/` page is canonical because:

- most facts already cited it;
- every quote used from the `/attractions/` copy also appears in its visible text;
- the `/attractions/` copies contain extra embedded (non-visible) content
  that conflicts with other official information (see section 7).

| Duplicate URL | Use instead | Facts moved |
|---------------|-------------|-------------|
| https://karnatakatourism.org/en/attractions/kali-tiger-reserve/ | S3 | FACT003 |
| https://karnatakatourism.org/en/attractions/hornbills-of-dandeli | S4 | FACT009 |

## 2. Fact record format

Every fact in `data/raw_facts.json` must have these fields:

| Field            | Type    | Meaning |
|------------------|---------|---------|
| `id`             | string  | Permanent ID, `FACTnnn`. Never reuse or renumber an ID. |
| `category`       | string  | One of the categories in section 3. |
| `fact`           | string  | One self-contained claim, worded as the source supports it. |
| `source`         | string  | Publisher name. |
| `source_url`     | string  | Canonical page containing the claim (section 1). |
| `confidence`     | string  | `high`, `medium` or `low`. |
| `time_sensitive` | boolean | `true` if the claim can change (section 5). |
| `status`         | string  | `verified`, `needs_review` or `rejected` (section 4). |

Optional fields:

- `verification_note`: what the reviewer found, with a short quote from the
  page, any re-citation, and any conflict. Expected for every
  `needs_review` or `rejected` fact and for every changed fact.
- `topic`: the old category field on FACT001–FACT015, kept for backward
  compatibility.

## 3. Categories

| Category      | Use for |
|---------------|---------|
| `attractions` | Sightseeing places: caves, rocks, viewpoints, landmarks. |
| `activities`  | Rafting, kayaking, coracle rides, safaris, birdwatching, trekking. |
| `wildlife`    | Animals, birds, habitats, protected-area ecology. |
| `travel`      | Getting there, nearest stations and airports, best season, trip planning. |
| `safety`      | Visitor safety rules, mandatory equipment, guidelines. |
| `geography`   | Location, district, rivers, protected-area boundaries. |
| `behaviour`   | Reserved. Behaviour examples (`BEHAVIOUR00n`) live in `data/train.jsonl`, not in `raw_facts.json`. |

Old `topic` values were mapped as follows: `adventure` → `activities`,
`nature` → `wildlife`, `transport` → `travel`.

## 4. Fact status and verification

- **`verified`**: a reviewer opened `source_url` and found the claim in the
  page's visible text, worded no more strongly than the page. Only verified
  facts are used to generate or approve training examples.
- **`needs_review`**: a candidate, a fact the cited page only partly
  supports, or a fact whose official sources conflict. These facts are
  excluded from generation and approval.
- **`rejected`**: not supported or outdated. Keep it for the record; never
  reuse its ID.

### Verification rules

1. Use official government sources (district administration, Karnataka
   Tourism, Karnataka Forest Department).
2. Find the claim in the page's **visible** text. Hidden, embedded or
   encoded content does not count as support.
3. Do not add numbers, dates or qualifiers the page does not state. Wording
   that changes the meaning (e.g. "dam water levels" vs "river water
   levels") must be fixed before the fact is verified.
4. Attribute claims that rest on the source's authority or are promotional
   ("Karnataka Tourism states that ...").
5. **Conflicts:** if official sources disagree, do not pick one. Set
   `needs_review`, describe the conflict in `verification_note`, and add it
   to section 7.
6. Never invent a URL. Cite the canonical page (section 1).
7. Do not record prices, fees, phone numbers or exact timings as facts.
8. A passing `validate_facts.py` run checks structure only. It is not
   verification; URL checks are format-only.

## 5. Time-sensitive information

Set `time_sensitive: true` when a claim can change without notice, for
example seasonal or permission-dependent availability, operating rules and
mandatory equipment, or transport details. Recheck these facts against
their source before each generation run, and do not present them as
guarantees.

## 6. Dataset workflow

```
raw_facts.json -> validate_facts.py -> generate_dataset.py -> drafts (needs_review)
  -> check_drafts.py -> review_manifest.py sync -> HUMAN REVIEW in review_manifest.json
  -> approved_dataset.py -> approved_train.jsonl
  -> prepare_final_dataset.py (+ behaviour examples from train.jsonl) -> final_train.jsonl
```

### 6.1 Example IDs

Every draft has a stable `example_id` = `<source_fact_id>-<8 hex chars>`,
where the hex is a hash of the normalised question (lowercase, collapsed
spaces, no trailing punctuation). Drafts written before IDs existed (the 30
in `generated_drafts.jsonl`) get the same ID from the same formula, so that
file did not need to be rewritten. The same question for the same fact
always gets the same ID.

### 6.2 Review manifest (`data/review_manifest.json`)

The manifest holds one entry per draft. You can edit it in any text editor:

```json
{
  "example_id": "FACT001-83d8e2c8",
  "source_fact_id": "FACT001",
  "question": "Where is Dandeli located?",
  "answer": "Dandeli is located in Uttara Kannada district, Karnataka, India.",
  "decision": "unreviewed",
  "reviewer": "",
  "reviewed_on": "",
  "notes": "",
  "answer_edit_reason": "",
  "content_hash": "8e54f51e047520e1"
}
```

- `decision`: `unreviewed` (default), `approved` or `rejected`. Only
  `approved` entries reach `approved_train.jsonl`.
- `approved` and `rejected` need `reviewer` and `reviewed_on` (YYYY-MM-DD).
- `content_hash` covers the fact ID, question and answer (not the system
  prompt). If a draft changes after review, its hash no longer matches and
  the approval stops working until the draft is reviewed again.
- `question`, `answer` and `content_hash` are read-only copies; scripts
  refresh them.

To review, either edit the JSON directly or use the CLI:

```
python ai/training/review_manifest.py set --decision approved --reviewer "Name" FACT001-83d8e2c8
python ai/training/review_manifest.py set --decision rejected --reviewer "Name" --notes "reason" FACT009-9606af01
```

Nothing is ever approved automatically. `sync` adds new drafts as
`unreviewed` and never changes an approved or rejected entry.

### 6.3 Intentional answer edits

Normally a draft answer must equal its fact text exactly. A deliberate
difference is allowed only when the manifest entry's `answer_edit_reason`
explains why the edited answer is still supported by the source, **and**
the entry's `content_hash` matches the current draft. `check_drafts.py`
lists these as "Reviewed answer edits". Any other difference, or a later
change to an edited answer, is an error.

Current reviewed edits:

| Example | Edit | Reason |
|---------|------|--------|
| FACT006-41f44fa1, FACT006-db5ee384 | Drops the "Uttara Kannada District Administration states that" attribution | Confirmed as an intentional edit by the project owner on 2026-11-19; S1 states "a National Wildlife Sanctuary in 1956". |

The FACT009 manual correction (adding the "Karnataka Tourism states that"
attribution) was moved into the fact itself. FACT009's drafts now match
their fact exactly, and no override is needed.

### 6.4 Building datasets

- `approved_dataset.py` includes an example only if it is approved in the
  manifest, its hash is unchanged, its fact is `verified`, and its answer
  matches the fact (or is a reviewed edit). An approved example whose fact
  was later downgraded is excluded with a warning.
- `prepare_final_dataset.py` checks every approved record against the
  manifest again and requires unique example IDs and unique questions. It
  also makes sure every record uses the canonical system prompt.
- Neither script has a fixed expected count. Both refuse to overwrite an
  existing output file without `--overwrite`, and both support `--dry-run`.

### 6.5 System prompt

There is one canonical system prompt, `CANONICAL_SYSTEM_PROMPT` in
`ai/training/pipeline_common.py`. It is the prompt the generator has always
used. The behaviour examples in `data/train.jsonl` use an older one-line
prompt, listed in `LEGACY_SYSTEM_PROMPTS`. `prepare_final_dataset.py`
replaces that known prompt with the canonical prompt when it builds
`final_train.jsonl`. Questions and answers are not changed, and any
unknown prompt is an error. `train.jsonl` itself is not rewritten.

`ai/evaluation/baseline.py` deliberately uses its own prompt for the
base-model baseline, and this pipeline does not change it.

### 6.6 Pipeline tests

Run every suite (use this after changing any pipeline script):

```
ai/.venv/Scripts/python.exe ai/training/tests/run_all.py
```

| Suite | Covers |
|-------|--------|
| `test_pipeline.py` | Review workflow: approve / reject / unreviewed, stale approvals, reviewed edits, duplicates, system-prompt migration. Runs on temporary copies of `data/` with review decisions reset, so it keeps working as the real review progresses. |
| `test_golden.py` | Stage 0 baseline (2026-11-20): pinned `make_example_id`, `content_hash` and `normalise_text` values for all 33 real examples plus edge and non-ASCII inputs; byte-identical snapshots of `approved_dataset.py` and `prepare_final_dataset.py`; manifest compatibility (28 approved, 2 rejected, 0 stale, 0 orphaned; old minimal-field entries still work); live check that `approved_train.jsonl` and `final_train.jsonl` equal a fresh rebuild and that every baseline draft and manifest entry is unchanged. |
| `test_quality_checks.py` | The advisory checks in `quality_checks.py` and the `dataset_report.py` CLI, on synthetic data in temporary folders, plus read-only regression checks on the baseline fixtures (section 6.8). |
| `run_all.py` | Runs every suite and fails if any file under `data/` was changed, added or removed during the run. |

The baseline fixtures in `ai/training/tests/fixtures/baseline_2026-11-20/`
are frozen copies of the Stage 0 inputs and outputs, with `golden.json`
(pinned values) and `SHA256SUMS.json`. Never edit them by hand. A golden or
snapshot failure means pipeline behaviour changed: investigate before
changing anything.

The live checks are expected to fail when `data/` changes legitimately but
outputs were not rebuilt (e.g. after new review decisions, run
`approved_dataset.py` and `prepare_final_dataset.py`). Live decision counts
are reported, not pinned, so re-reviewing the two pending rejections will
not break the suite.

Snapshots are byte-identical on Windows, where the baseline was recorded
(the scripts write CRLF line endings there); on other platforms the
comparison ignores only line endings.

### 6.7 Generating new drafts

`generate_dataset.py` skips any example whose ID or question already exists
in `data/generated_drafts.jsonl`. A new output file therefore holds only new
drafts, and reviewed or hand-corrected drafts are never duplicated or
replaced.

### 6.8 Dataset quality report (advisory)

```
ai/.venv/Scripts/python.exe ai/training/dataset_report.py
ai/.venv/Scripts/python.exe ai/training/dataset_report.py --dataset data/generated_drafts.jsonl
```

`dataset_report.py` runs the checks in `ai/training/quality_checks.py` and
prints a report: counts, knowledge/behaviour share, examples per fact,
answer repetition and lengths, exact and near-duplicate questions,
unsupported entity indicators, evaluation overlap, traceability, and a
numbered list of warnings for human review. Defaults: `data/final_train.jsonl`
checked against `raw_facts.json`, `review_manifest.json` and
`nirva_eval.json`.

- **Advisory only.** It never changes, removes, merges, approves or rejects
  anything, and no pipeline script calls it. It writes nothing unless
  `--json FILE` is given, and then only to a new file.
- **Warnings** need a person to look; **info** notes are context.
- **Provisional thresholds** (calibrated on the 30 baseline drafts only):
  near-duplicate when same-fact character 3-gram Jaccard ≥ 0.60 or
  content-word Jaccard ≥ 0.75, or different-fact character ≥ 0.50; eval
  overlap at character ≥ 0.50 or content-word ≥ 0.75; an answer text used
  more than 4 times; a fact with more than 2× the median examples;
  behaviour share outside 12–25%.
- **Behaviour share is dataset-aware.** The 12–25% target applies to the
  final dataset. It is checked for `final` inputs (where zero behaviour
  examples is flagged) and for any input that contains behaviour examples.
  For drafts or approved-only files without behaviour examples the report
  says "Not applicable — behaviour examples are not present in this
  dataset" and calculates no percentage.
- **Entity indicators are heuristic.** Capitalised names and numbers are
  compared with the linked fact's text and publisher (behaviour examples:
  only Dandeli, Uttara Kannada, Karnataka, India). Lowercase names (animals,
  birds) are not detected. A flag means "not found in the recorded fact",
  not "false": the source page may still support it.
- **Eval overlap compares wording only.** Questions that ask the same thing
  in different words are not detected.

## 7. Unresolved conflicts register

| Topic | Source A | Source B | Status |
|-------|----------|----------|--------|
| Nearest railway station | S1: "Nearest Railway Station at Alnavar junction" (visible text) | Embedded, non-visible base64 content on Karnataka Tourism `/attractions/` pages: "Londa is the nearest railway station ( 35 Kms )" (hornbills page) and "Hubli Railway Station is the nearest railway station ( 112 Kms )" (Kali Tiger Reserve page). These were hand-decoded and are unconfirmed. | FACT014 set to `needs_review` and excluded until an official source settles it. |
| Dandeli Wildlife Sanctuary area | S1: "The sanctuary now covers an area of 834.16 square kilometres." (page last updated 26.12.2022) | S3: "Dandeli Wildlife Sanctuary (475.018 Km²)" | No fact recorded. Do not add an area fact until the difference is explained (e.g. by a Forest Department notification). FACT022 (S1: "This sanctuary is the second largest wildlife sanctuary of Karnataka.") depends on the area, so it stays `needs_review` until this is resolved. |

FACT005 still has only partial support. On 2026-11-20 it was re-cited from S4
to S2, which says "The sanctuary is a haven for diverse flora and fauna." and
"Over 300 bird species call Dandeli home." S2 does not mention hornbills, so
the fact stays `needs_review` until a superseding fact is worded as S2 states it.

FACT013 is `rejected`. It was superseded on 2026-11-20 by FACT026, which uses
S5's wording ("dam water levels", not "river water levels"). FACT013's text was
left unchanged so that its existing drafts and review entries stay consistent.

FACT020, FACT021, FACT022, FACT025 and FACT026 are `needs_review` candidates
from the Day 2 audit. Each records its exact page quote and waits for the
project owner's confirmation (section 10).

FACT010 is `verified`: the project owner independently checked its source
and confirmed the status on 2026-11-20. FACT016–FACT019 are `verified`: the
project owner completed their source verification and confirmed the status
on 2026-11-20. (Their `verification_note` text predates these confirmations
and has not been rewritten.)

## 8. Data files

| File | Purpose |
|------|---------|
| `raw_facts.json` | Curated facts (source of truth for answers). |
| `generated_drafts.jsonl` | Generated drafts, including the reviewed manual corrections. Never regenerate it in place. |
| `review_manifest.json` | Human review decisions per example. |
| `approved_train.jsonl` | Output of `approved_dataset.py`: 22 human-approved knowledge examples with example IDs. Verified on 2026-11-20 as byte-identical to a fresh build from the current manifest and facts (see section 10). |
| `train.jsonl` | Original hand-written examples. Only the `BEHAVIOUR` examples are used in the final dataset. |
| `final_train.jsonl` | Output of `prepare_final_dataset.py`: 25 examples (22 knowledge, 3 behaviour), one canonical system prompt. Rebuilt on 2026-11-20 (section 10). |
| `archive/final_train.2026-11-18.jsonl` | The previous 33-example `final_train.jsonl`, built from the old auto-approved data. Kept for reference only; never train on it. |
| `raw_facts.json.bak` | Older copy of `raw_facts.json` (2026-11-19) in which FACT016–FACT019 had the invalid status `"approved"`. It fails `validate_facts.py`. Historical only; never use it as input. |
| `validation.jsonl` | **Intended:** the validation split used during LoRA fine-tuning to monitor validation loss (ARCHITECTURE.md §3.3, step 6). It should hold examples in the same format as `final_train.jsonl`, taken from reviewed and approved examples and kept out of the training split. **Current state:** empty, and no script reads or writes it yet. Do not fill it with invented examples. |
| `nirva_eval.json` | Held-out evaluation questions. Never edit it and never use it in training. It is separate from `validation.jsonl`: one is for evaluation, the other is a training-time validation split. |

## 9. Data quality rules

- Prefer official government sources.
- Record the source for every factual claim.
- Do not invent prices, phone numbers or timings.
- Treat seasonal activities as variable.
- Recheck time-sensitive information before using it.
- Resolve conflicts with evidence, never by choosing arbitrarily.

## 10. Dataset state log

### 2026-11-20: Stage 0 baseline rebuild

No drafts were generated and no review decisions or fact statuses were changed.

- Checks run: `test_pipeline.py` (32/32 passed), `validate_facts.py`,
  `check_drafts.py`, `review_manifest.py status` and `sync --dry-run`
  (30 entries: 28 approved, 2 rejected, 0 unreviewed, 0 stale, 0 orphaned).
- `approved_train.jsonl` was not rebuilt: a fresh build was byte-identical
  to the existing file (22 examples).
- `final_train.jsonl` was rebuilt from `approved_train.jsonl` plus the three
  `BEHAVIOUR` examples from `train.jsonl`: 33 → 25 examples. The old file is
  in `archive/final_train.2026-11-18.jsonl`.
- Removed (8), because the current pipeline does not approve them:

  | Source fact | Question | Reason |
  |-------------|----------|--------|
  | FACT005 | Which notable bird group is found in Dandeli Wildlife Sanctuary? | Fact is `needs_review` |
  | FACT005 | Are hornbills found in Dandeli Wildlife Sanctuary? | Fact is `needs_review` |
  | FACT013 | What factors affect rafting operations in Dandeli? | Fact is `needs_review` |
  | FACT013 | Does rafting availability in Dandeli depend on river flow and permissions? | Fact is `needs_review` |
  | FACT014 | Which railway station is identified for reaching Dandeli? | Fact is `needs_review` (unresolved conflict, section 7) |
  | FACT014 | Can travellers use Alnavar Junction to reach Dandeli? | Fact is `needs_review` (unresolved conflict, section 7) |
  | FACT009 | What is notable about hornbill diversity in Kali Tiger Reserve? | Rejected in manifest (FACT009-9606af01) |
  | FACT010 | Is Syntheri Rocks a natural attraction in the Kali Tiger Reserve region? | Rejected in manifest (FACT010-a4b9ebb6) |

- The three behaviour examples kept their questions and answers; only their
  system prompt was migrated to the canonical prompt, and they gained
  `example_id`s (BEHAVIOUR001-2474be68, BEHAVIOUR002-51129a89,
  BEHAVIOUR003-89bb7516).

**Pending human action:**

- FACT009-9606af01 and FACT010-a4b9ebb6 were rejected with reviewer
  "Claude Code (data-quality pass)", not by a person. They need a fresh
  human re-review. Until then the rejections stand and both stay excluded.
- FACT005, FACT013 and FACT014 still have `approved` manifest entries. They
  are excluded only because the facts are `needs_review`; if a fact is set
  back to `verified` without a text change, those approvals take effect
  again with no new review. Re-review them when the facts are resolved.
- Behaviour examples are 3 of 25 (12%), the bottom of the 12–25% target.
  They have not been through the review manifest.
- `nirva_eval.json` overlaps the training data (4 of 6 questions are close
  to training questions). A separate `nirva_eval_v2.json` is planned; the
  existing file stays unchanged.

### 2026-11-20: Day 2 source audit

Only `raw_facts.json` and this file changed. No drafts were generated, and
no review decisions or training files were changed.

**Method.** The audit document proposing these changes quoted page text it
had not read. Its quotes came from AI-generated web-search summaries that mixed
official pages with third-party sites. Those quotes were not accepted as
evidence. Every claim was re-checked against the visible text of the cited
page, fetched directly on 2026-11-20. Hidden, embedded and alt-text content
was ignored.

| Audit item | Outcome | Evidence (visible text) |
|------------|---------|-------------------------|
| FACT013 wording | Superseded by **FACT026** (`needs_review`); FACT013 set to `rejected`, text unchanged | S5: "Pre-booking is advised, and slots are allocated based on dam water levels and forest department clearance." |
| FACT005 citation | Re-cited S4 → S2; stays `needs_review` (hornbills not on S2) | S2: "The sanctuary is a haven for diverse flora and fauna." |
| FACT014 | Unchanged: `needs_review`, conflict open (section 7) | S1 still: "Nearest Railway Station at Alnavar junction" |
| "S7" kalitigerreserve.org | **Not registered**: provenance not verified (section 1) | No official or Forest Department statement on the site |
| FACT020 Shiroli Peak | Added, `needs_review`. The audit's "located within the sanctuary" was dropped as unsupported. | S2: "Shiroli Peak offers panoramic views of the Western Ghats." |
| FACT021 Road distances | Added, `needs_review` | S1: "By road : Dharwad – 57 Kms, Hubballi – 72 Kms" |
| FACT022 Second largest | Added, `needs_review`, linked to the area conflict | S1: "This sanctuary is the second largest wildlife sanctuary of Karnataka." |
| FACT023 Kulgi Nature Camp | **Not added**: its only source is the unverified site, which also does not say who manages the camp | — |
| FACT024 Crocodile Park | **Not added**: not on S2, and not in S1's visible text | — |
| FACT025 Coracle rides | Added, `needs_review`. The audit's "traditional" was dropped as unsupported. | S2: river activities list including "Coracle rides" |

**IDs.** FACT023 and FACT024 were proposed but not added. They are reserved
and must never be reused. The fact base now holds 24 records: 16 `verified`,
7 `needs_review` and 1 `rejected`.

**Training data.** No change. New and `needs_review` facts have no drafts. A
verified fact enters training only after drafts are generated, reviewed and
approved.

**Pending human action:**

- Confirm or reject the candidates FACT020, FACT021, FACT025 and FACT026
  against their pages. FACT022 waits on the area conflict.
- FACT012 (`verified`, in training) says "designated stretches of the Kali
  River". S5 says "Rafting is conducted on regulated stretches of the Kali
  River". The meaning is close but the wording differs. Decide whether it
  needs a superseding fact.
