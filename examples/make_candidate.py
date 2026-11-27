"""Build ONLY the openly synthetic teaching candidate, not a scientific extractor."""
import argparse
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # Keep generated binary caches outside the text-only submission.

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--corpus", required=True)
parser.add_argument("--out", required=True)
args = parser.parse_args()
script = Path(__file__).resolve().parents[1] / "scripts" / "nanopub.py"
spec = importlib.util.spec_from_file_location("nanopub_demo_helpers", script)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
corpus = helper.read_json(args.corpus)
quotes = [
    "In a synthetic experiment with 40 simulated samples, method A reduced median runtime from 10 ms to 8 ms compared with method B on dataset D.",
    "On the same dataset D, the accuracy difference between method A and method B was not statistically significant (p = 0.31).",
]
evidence = []
for i, quote in enumerate(quotes, 1):
    matches = helper.locate(corpus, quote)
    if len(matches) != 1:
        raise SystemExit("Use only examples/source.txt: exactly one matching synthetic span per claim is required.")
    evidence.append(dict(matches[0], evidence_id=f"e{i}", role="supports"))
candidate = {
    "case_id": "DEMO-SYNTHETIC-ONLY",
    "status": "success",
    "task_summary": "DEMO ONLY: split two synthetic findings and bind original teaching text. No real scientific result or official score.",
    "assertions": [
        {
            "assertion_id": "a1", "text": "For 40 simulated samples on dataset D, method A reduced median runtime from 10 ms (method B) to 8 ms.",
            "subject": "method A", "relation": "decreases", "object": "median runtime",
            "polarity": "positive", "qualifiers": {"sample_size": 40, "sample_type": "simulated", "dataset": "D", "comparator": "method B", "baseline": "10 ms", "observed": "8 ms"},
            "support": "direct", "evidence_ids": ["e1"],
            "confidence": {"level": "high", "basis": "The synthetic sentence directly reports the same metric, comparator, dataset and sample count; this is not external validity."},
            "review": {"atomic": True, "scope_checked": True, "entailment": "supports", "rationale": "One runtime comparison, with simulation, dataset and metric preserved."}
        },
        {
            "assertion_id": "a2", "text": "On dataset D, no statistically significant accuracy difference was reported between method A and method B (p = 0.31).",
            "subject": "method A versus method B", "relation": "no_detected_difference", "object": "accuracy",
            "polarity": "uncertain", "qualifiers": {"dataset": "D", "p_value": "0.31", "interpretation": "nonsignificance, not equivalence"},
            "support": "direct", "evidence_ids": ["e2"],
            "confidence": {"level": "high", "basis": "Directly quotes the synthetic significance result, without asserting equal accuracy."},
            "review": {"atomic": True, "scope_checked": True, "entailment": "supports", "rationale": "One reported statistical finding; does not infer equivalence or absence of effect."}
        }
    ],
    "evidence": evidence,
    "coverage": [{"requirement": "DEMO ONLY: two independent findings", "status": "covered", "assertion_ids": ["a1", "a2"], "evidence_ids": ["e1", "e2"], "reason": "Each synthetic sentence maps to an independently reviewable claim."}],
    "uncertainty": [],
    "change_log": [{"change": "Created openly synthetic demo candidate.", "reason": "Demonstrate the interface; no official case was supplied."}]
}
helper.write_json(args.out, candidate)
print("Created synthetic teaching candidate; not an official case answer.")
