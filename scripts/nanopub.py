#!/usr/bin/env python3
"""Evidence ledger helpers. Semantic extraction and entailment remain Agent work."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path

VERSION = "1.0.0"
RELATIONS = {"reports", "compares", "associated_with", "increases", "decreases",
             "no_detected_difference", "causes", "improves", "worsens", "measures",
             "uses", "predicts", "supports", "contradicts", "other"}
STATUSES = {"success", "partial", "cannot_determine", "refused", "failed"}
COVERAGE = {"covered", "partial", "not_reported", "cannot_determine",
            "material_missing", "execution_failure"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")
    temp.replace(path)


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def prepare(paths):
    sources, seen = [], set()
    for item in paths:
        path = Path(item).resolve()
        if str(path) in seen:
            continue
        seen.add(str(path))
        source = {"source_id": "src-" + hashlib.sha256(str(path).encode()).hexdigest()[:16],
                  "path": str(path), "sha256": None, "status": "missing", "parser": None,
                  "metadata": {"title": None, "authors": [], "year": None,
                               "doi": None, "version": None},
                  "segments": [], "diagnostics": []}
        try:
            source["sha256"] = digest(path)
            # Same bytes at two distinct paths remain separate locatable sources.
            source["source_id"] = "src-" + hashlib.sha256(
                (str(path) + source["sha256"]).encode()).hexdigest()[:16]
            if path.suffix.lower() == ".pdf":
                try:
                    import pypdf
                except ImportError:
                    source["status"] = "unreadable"
                    source["diagnostics"].append("PDF parser missing: install pypdf or use the actual runtime parser.")
                    sources.append(source)
                    continue
                reader = pypdf.PdfReader(path)
                if reader.is_encrypted and not reader.decrypt(""):
                    raise ValueError("Encrypted PDF requires a password; no extraction performed.")
                pages = [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]
                source["parser"] = "pypdf/" + pypdf.__version__
                source["page_count"] = len(pages)
                source["empty_pages"] = [i for i, text in pages if not text.strip()]
                if source["empty_pages"]:
                    source["diagnostics"].append("Empty text pages require visual review/OCR; blank pages cannot be distinguished automatically.")
                source["status"] = "needs_ocr" if source["empty_pages"] else "ready"
                source["diagnostics"].append("PDF text order and table layout require visual confirmation; no OCR is performed.")
            elif path.suffix.lower() in {".txt", ".md"}:
                pages = [(None, path.read_text(encoding="utf-8-sig"))]
                source["parser"] = "utf-8-text/stdlib"
                source["status"] = "ready" if pages[0][1].strip() else "needs_ocr"
            else:
                raise ValueError("Unsupported input; use actual PDF or UTF-8 .txt/.md. Do not rename binary files.")
            for page, text in pages:
                # Paragraph indexes are parser paragraphs, never claimed to be publisher paragraph numbers.
                parts = re.split(r"\n[ \t]*\n+", text.replace("\r\n", "\n").replace("\r", "\n"))
                for number, part in enumerate(parts, 1):
                    if part.strip():
                        source["segments"].append({"segment_id": f"p{page or 0:04d}-b{number:04d}",
                                                   "page": page, "paragraph": number,
                                                   "kind": "text", "text": part})
        except FileNotFoundError:
            source["diagnostics"].append("Source file missing.")
        except Exception as exc:
            source["status"] = "unreadable"
            source["diagnostics"].append(f"{type(exc).__name__}: {exc}")
        sources.append(source)
    return {"schema_version": "1.0", "tool_version": VERSION, "sources": sources,
            "notes": "Extraction only; file names and PDF metadata are not scientific facts. Offsets count Unicode characters."}


def locate(corpus, quote, source_id=None):
    if not quote:
        raise ValueError("Quote must not be empty.")
    found = []
    for source in corpus["sources"]:
        if source_id and source["source_id"] != source_id:
            continue
        for segment in source["segments"]:
            start = segment["text"].find(quote)
            while start >= 0:
                found.append({"source_id": source["source_id"], "segment_id": segment["segment_id"],
                              "page": segment["page"], "paragraph": segment["paragraph"],
                              "start": start, "end": start + len(quote), "quote": quote})
                start = segment["text"].find(quote, start + 1)
    return found


def verify(corpus, candidate):
    errors, warnings = [], []

    def err(code, path, message):
        errors.append({"code": code, "path": path, "message": message})

    def warn(code, path, message):
        warnings.append({"code": code, "path": path, "message": message})

    def text_fields(obj, names, path):
        for name in names:
            if not isinstance(obj.get(name), str) or not obj[name].strip():
                err("required_text", path + "." + name, "Nonempty string required.")

    def index(items, key, path):
        result = {}
        if not isinstance(items, list):
            err("required_list", path, "Expected a list.")
            return result
        for i, item in enumerate(items):
            if not isinstance(item, dict):
                err("object_required", f"{path}[{i}]", "Expected an object.")
                continue
            value = item.get(key)
            if not isinstance(value, str) or not value.strip():
                err("missing_id", f"{path}[{i}]", f"Missing {key}.")
            elif value in result:
                err("duplicate_id", f"{path}[{i}]", f"Duplicate {key}: {value}")
            else:
                result[value] = item
        return result

    if not isinstance(corpus, dict) or not isinstance(candidate, dict):
        return {"valid": False, "errors": [{"code": "object_required", "path": "$", "message": "Corpus and candidate must be objects."}], "warnings": []}
    text_fields(candidate, ["task_summary"], "candidate")
    case_id = candidate.get("case_id")
    if not ((isinstance(case_id, str) and case_id.strip()) or type(case_id) is int):
        err("case_id", "candidate.case_id", "Preserve an original nonempty string or integer case identifier.")
    status = candidate.get("status")
    if status not in STATUSES:
        err("invalid_status", "candidate.status", "Unknown status.")
    sources = index(corpus.get("sources"), "source_id", "corpus.sources")
    assertions = index(candidate.get("assertions"), "assertion_id", "candidate.assertions")
    evidence = index(candidate.get("evidence"), "evidence_id", "candidate.evidence")
    coverage = candidate.get("coverage")
    uncertainty = candidate.get("uncertainty")
    changes = candidate.get("change_log")
    for key in ("coverage", "uncertainty", "change_log"):
        if not isinstance(candidate.get(key), list):
            err("required_list", "candidate." + key, "Expected a list.")
    if not coverage:
        err("missing_coverage", "candidate.coverage", "Record each actual task requirement and its outcome.")
    if not changes:
        err("missing_changes", "candidate.change_log", "Record actual creation or edits with reasons.")
    if isinstance(changes, list):
        for i, change in enumerate(changes):
            if not isinstance(change, dict):
                err("object_required", f"change_log[{i}]", "Expected change and reason.")
            else:
                text_fields(change, ["change", "reason"], f"change_log[{i}]")
    if isinstance(uncertainty, list):
        for i, item in enumerate(uncertainty):
            if not isinstance(item, dict):
                err("object_required", f"uncertainty[{i}]", "Expected an uncertainty object.")
            else:
                text_fields(item, ["code", "message"], f"uncertainty[{i}]")
    if not assertions and status == "success":
        err("empty_success", "candidate.assertions", "Cannot claim a completed extraction with no assertions.")
    if status != "success" and not uncertainty:
        err("missing_uncertainty", "candidate.uncertainty", "Explain limits and the human handoff for a nonsuccess result.")
    segments = {}
    for sid, source in sources.items():
        if source.get("status") not in {"ready", "needs_ocr", "missing", "unreadable"}:
            err("source_status", sid, "Invalid extraction status.")
        try:
            current = digest(source.get("path", ""))
            if current != source.get("sha256"):
                err("source_changed", sid, "File hash differs; re-prepare and rebind evidence.")
            else:
                fresh = prepare([source.get("path")])["sources"][0]
                if fresh["segments"] != source.get("segments") or fresh["status"] != source.get("status"):
                    err("corpus_changed", sid, "Stored extraction differs from re-reading the actual source. Re-prepare; do not edit the corpus.")
        except (OSError, TypeError):
            if source.get("status") not in {"missing", "unreadable"}:
                err("source_unavailable", sid, "Cannot reopen original source.")
        if source.get("status") != "ready":
            warn("source_incomplete", sid, str(source.get("diagnostics", [])))
            if status == "success":
                err("incomplete_success", sid, "Resolve source extraction gaps or report partial status.")
            if not uncertainty:
                err("missing_uncertainty", sid, "Explain missing/failed/OCR material.")
        segments[sid] = index(source.get("segments"), "segment_id", sid + ".segments")
    for eid, ev in evidence.items():
        text_fields(ev, ["source_id", "segment_id", "quote"], eid)
        sid = ev.get("source_id")
        segment = segments.get(sid, {}).get(ev.get("segment_id"))
        if not segment:
            err("unknown_segment", eid, "Source/segment reference does not exist.")
            continue
        if ev.get("role") not in {"supports", "contradicts", "context"}:
            err("evidence_role", eid, "Use supports, contradicts or context.")
        start, end = ev.get("start"), ev.get("end")
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(segment["text"]):
            err("invalid_offsets", eid, "Offsets must select a nonempty Unicode character span.")
        elif segment["text"][start:end] != ev.get("quote"):
            err("quote_mismatch", eid, "Quote must exactly equal the selected original text.")
        if "page" in ev and ev["page"] != segment.get("page"):
            err("page_mismatch", eid, "Use the segment's physical PDF page, not a guessed printed page.")
        if len(ev.get("quote", "")) > 2000:
            warn("long_evidence", eid, "Review minimal sufficiency; long spans may contain multiple claims.")
    fingerprints = {}
    for aid, claim in assertions.items():
        text_fields(claim, ["text", "subject", "relation", "object"], aid)
        if claim.get("relation") not in RELATIONS:
            err("unknown_relation", aid, "Relation must use the controlled vocabulary.")
        if claim.get("relation") == "other":
            text_fields(claim, ["relation_label"], aid)
        if claim.get("polarity") not in {"positive", "negative", "uncertain"}:
            err("invalid_polarity", aid, "Use positive, negative or uncertain.")
        if not isinstance(claim.get("qualifiers"), dict):
            err("qualifiers", aid, "Provide an object, even if no conditions were reported.")
        support = claim.get("support")
        if support not in {"direct", "inferred", "contradicted", "insufficient"}:
            err("support", aid, "Invalid support category.")
        refs = claim.get("evidence_ids")
        if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
            err("evidence_refs", aid, "Expected a list of evidence IDs.")
            refs = []
        for ref in refs:
            if ref not in evidence:
                err("unknown_evidence", aid, f"Evidence not found: {ref}")
        roles = {evidence[x].get("role") for x in refs if x in evidence}
        if support in {"direct", "inferred"} and "supports" not in roles:
            err("no_support", aid, "Supported/inferred assertions need supporting evidence.")
        if support == "contradicted" and "contradicts" not in roles:
            err("no_contradiction", aid, "A contradicted assertion needs the contrary evidence.")
        if "contradicts" in roles and support not in {"contradicted", "insufficient"}:
            err("hidden_conflict", aid, "Contrary evidence cannot be exported as an unqualified supported fact.")
        if support in {"contradicted", "insufficient"}:
            if status == "success":
                err("unsupported_success", aid, "Unresolved claims require partial/cannot_determine status.")
            if not uncertainty:
                err("missing_uncertainty", aid, "Describe unresolved support or conflict.")
        if support == "inferred":
            text_fields(claim, ["derivation"], aid)
        confidence = claim.get("confidence")
        if not isinstance(confidence, dict):
            err("confidence", aid, "Use level and an evidence-based basis, not invented probability.")
        else:
            if confidence.get("level") not in {"high", "medium", "low", "undetermined"}:
                err("confidence_level", aid, "Invalid confidence level.")
            text_fields(confidence, ["basis"], aid + ".confidence")
            if support in {"inferred", "contradicted", "insufficient"} and confidence.get("level") == "high":
                err("confidence_overstated", aid, "Reserve high for directly supported claims with complete scope.")
        review = claim.get("review")
        if not isinstance(review, dict):
            err("semantic_review", aid, "Agent must record atomicity, scope and entailment review.")
        else:
            if review.get("atomic") is not True or review.get("scope_checked") is not True:
                err("semantic_review", aid, "Split compound claims and check conditions before export.")
            expected = "supports" if support in {"direct", "inferred"} else "contradicts" if support == "contradicted" else "unclear"
            if review.get("entailment") != expected:
                err("entailment_review", aid, "Entailment review disagrees with support category.")
            text_fields(review, ["rationale"], aid + ".review")
        # Exact structured duplicates only. Different scopes, polarity or support are kept separate.
        fp = json.dumps({k: claim.get(k) for k in ("text", "subject", "relation", "relation_label", "object", "polarity", "qualifiers", "support")}, sort_keys=True, ensure_ascii=False)
        if fp in fingerprints:
            err("duplicate_assertion", aid, f"Merge exact duplicate with {fingerprints[fp]}, retaining every evidence ID.")
        fingerprints[fp] = aid
    if isinstance(coverage, list):
        for i, row in enumerate(coverage):
            key = f"coverage[{i}]"
            if not isinstance(row, dict):
                err("object_required", key, "Expected a coverage object.")
                continue
            text_fields(row, ["requirement", "reason"], key)
            if row.get("status") not in COVERAGE:
                err("coverage_status", key, "Unknown coverage state.")
            if row.get("status") != "covered" and status == "success":
                err("coverage_incomplete", key, "Uncovered requirements cannot be marked success.")
            if row.get("status") == "covered" and not row.get("assertion_ids"):
                err("unsubstantiated_coverage", key, "Covered extraction requirements need assertion references.")
            for field, lookup in (("assertion_ids", assertions), ("evidence_ids", evidence)):
                refs = row.get(field)
                if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
                    err("coverage_refs", key + "." + field, "Expected ID list.")
                else:
                    for ref in refs:
                        if ref not in lookup:
                            err("unknown_reference", key, f"Unknown {field}: {ref}")
    metadata = candidate.get("source_metadata", [])
    if not isinstance(metadata, list):
        err("metadata", "source_metadata", "Expected list.")
    else:
        seen_meta = set()
        for i, row in enumerate(metadata):
            key = f"source_metadata[{i}]"
            if not isinstance(row, dict):
                err("metadata", key, "Expected metadata object.")
                continue
            sid = row.get("source_id")
            if sid not in sources or sid in seen_meta:
                err("metadata_source", key, "Unknown or duplicate source.")
            seen_meta.add(sid)
            if not isinstance(row.get("authors", []), list):
                err("metadata_authors", key, "Use an author list, no guessed author strings.")
            refs = row.get("metadata_evidence", [])
            if not isinstance(refs, list) or any(not isinstance(x, str) for x in refs):
                err("metadata_refs", key, "Expected evidence ID list.")
                refs = []
            has_fact = any(row.get(k) for k in ("title", "authors", "year", "doi", "version"))
            if has_fact and not refs:
                err("metadata_unlocated", key, "Nonempty metadata needs original-source evidence.")
            for ref in refs:
                if ref not in evidence or evidence[ref].get("source_id") != sid:
                    err("metadata_wrong_source", key, "Metadata evidence must reference this source.")
    warn("semantic_limit", "$", "Exact text, hashes and references were checked. Scientific truth, entailment, atomicity, missing contrary evidence and metadata meaning require Agent/visual review.")
    return {"valid": not errors, "tool_version": VERSION, "errors": errors,
            "warnings": warnings, "counts": {"sources": len(sources), "assertions": len(assertions), "evidence": len(evidence)}}


def contract_errors(contract, payload, path="$"):
    """Conservative contract support. Never silently certify unknown schema keywords."""
    errors = []
    if isinstance(contract, list):
        keys = [x if isinstance(x, str) else x.get("name") if isinstance(x, dict) else None for x in contract]
        if any(not isinstance(k, str) for k in keys):
            return ["Unsupported contract list: adapt manually to the actual platform instructions."]
        return [f"{path}: missing contract field {k}" for k in keys if k not in payload]
    if contract is True or contract == {}:
        return []
    if contract is False:
        return [f"{path}: schema rejects every value"]
    if not isinstance(contract, dict):
        return ["Unsupported or empty output_contract; inspect actual instructions."]
    schema_keys = {"type", "properties", "required", "items", "enum", "const", "additionalProperties", "$schema", "$id", "title", "description", "examples", "default", "minItems", "maxItems", "minLength", "maxLength", "minimum", "maximum"}
    if not (schema_keys & set(contract)):
        return [f"{path}: missing contract field {k}" for k in contract if k not in payload]
    unknown = set(contract) - schema_keys
    if unknown:
        errors.append(f"{path}: unsupported schema keywords {sorted(unknown)}; use the platform validator or resolve explicitly.")
    types = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool, "null": type(None)}
    declared = contract.get("type")
    if declared:
        permitted = declared if isinstance(declared, list) else [declared]
        def matches(name):
            cls = types.get(name)
            return cls is not None and isinstance(payload, cls) and not (name in {"integer", "number"} and isinstance(payload, bool))
        if not any(matches(t) for t in permitted):
            return errors + [f"{path}: expected {declared}"]
    if "enum" in contract and payload not in contract["enum"]:
        errors.append(f"{path}: not in enum")
    if "const" in contract and payload != contract["const"]:
        errors.append(f"{path}: const mismatch")
    if isinstance(payload, dict):
        properties = contract.get("properties", {})
        for name in contract.get("required", []):
            if name not in payload:
                errors.append(f"{path}: missing required field {name}")
        for name, value in payload.items():
            if name in properties:
                errors += contract_errors(properties[name], value, path + "." + name)
            elif contract.get("additionalProperties") is False:
                errors.append(f"{path}: additional field {name}")
            elif isinstance(contract.get("additionalProperties"), dict):
                errors += contract_errors(contract["additionalProperties"], value, path + "." + name)
    if isinstance(payload, list):
        if "items" in contract:
            for i, value in enumerate(payload):
                errors += contract_errors(contract["items"], value, f"{path}[{i}]")
        for name, op in (("minItems", lambda n: len(payload) < n), ("maxItems", lambda n: len(payload) > n)):
            if name in contract and op(contract[name]):
                errors.append(f"{path}: violates {name}")
    if isinstance(payload, str):
        for name, op in (("minLength", lambda n: len(payload) < n), ("maxLength", lambda n: len(payload) > n)):
            if name in contract and op(contract[name]):
                errors.append(f"{path}: violates {name}")
    if type(payload) in (int, float):
        if "minimum" in contract and payload < contract["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in contract and payload > contract["maximum"]:
            errors.append(f"{path}: above maximum")
    return errors


def finalize(corpus, candidate, out_path, case=None):
    if not isinstance(corpus, dict) or not isinstance(candidate, dict):
        raise ValueError("Corpus and candidate must be JSON objects.")
    if case is not None and not isinstance(case, dict):
        raise ValueError("Case must be a JSON object.")
    report = verify(corpus, candidate)
    official = None
    if case is not None:
        if candidate.get("case_id") != case.get("case_id"):
            report["errors"].append({"code": "case_id", "path": "case_id", "message": "Must exactly match original case_id."})
        if "output_contract" in case:
            official = copy.deepcopy(candidate.get("contract_result"))
            problems = []
            if not isinstance(official, dict):
                problems = ["Provide contract_result using the actual task's output_contract fields."]
            else:
                if "case_id" in official and official["case_id"] != case.get("case_id"):
                    problems.append("contract_result.case_id differs from actual case_id.")
                formal_status = official.get("status")
                if isinstance(formal_status, str) and formal_status in STATUSES and formal_status != candidate.get("status"):
                    problems.append("contract_result.status contradicts the canonical evidence ledger status.")
                if candidate.get("status") != "success" and isinstance(formal_status, str) and formal_status.lower() in {"completed", "complete", "ok", "succeeded"}:
                    problems.append("A nonsuccess evidence ledger cannot be exported with a success-equivalent formal status.")
                official["case_id"] = case.get("case_id")
                problems += contract_errors(case["output_contract"], official)
            for problem in problems:
                report["errors"].append({"code": "output_contract", "path": "contract_result", "message": problem})
    report["valid"] = not report["errors"]
    core = {k: copy.deepcopy(candidate.get(k)) for k in ("case_id", "status", "task_summary", "assertions", "evidence", "coverage", "uncertainty", "change_log")}
    core["schema_version"] = "1.0"
    core["validation"] = report
    raw_sources = corpus.get("sources", [])
    core["sources"] = copy.deepcopy([s for s in raw_sources if isinstance(s, dict)] if isinstance(raw_sources, list) else [])
    metadata_rows = candidate.get("source_metadata", [])
    meta = {x["source_id"]: x for x in (metadata_rows if isinstance(metadata_rows, list) else []) if isinstance(x, dict) and isinstance(x.get("source_id"), str)}
    for source in core["sources"]:
        raw_segments = source.pop("segments", [])
        source["segment_index"] = [{k: s.get(k) for k in ("segment_id", "page", "paragraph", "kind")} for s in (raw_segments if isinstance(raw_segments, list) else []) if isinstance(s, dict)]
        if source.get("source_id") in meta:
            source["metadata"] = {k: v for k, v in meta[source["source_id"]].items() if k != "source_id"}
    if not report["valid"]:
        core["status"] = "partial" if core.get("assertions") else "cannot_determine"
        if not isinstance(core.get("uncertainty"), list):
            core["uncertainty"] = []
        core["uncertainty"].append({"code": "validation_failed", "message": "Export checks failed; correct the listed errors. This is a recovery artifact, not a validated formal answer."})
        if isinstance(official, dict):
            core["unvalidated_contract_draft"] = official
    parent = Path(out_path).parent
    reserved = {"nanopublications.json", "validation.json"}
    if Path(out_path).name in reserved:
        raise ValueError("--out cannot use a reserved sidecar filename.")
    write_json(parent / "nanopublications.json", core)
    write_json(parent / "validation.json", report)
    write_json(out_path, official if report["valid"] and official is not None else core)
    return report


def package_check(root):
    root = Path(root).resolve()
    errors, count, total = [], 0, 0
    if not (root / "SKILL.md").is_file():
        errors.append("SKILL.md missing at submission root.")
    for path in root.rglob("*"):
        if path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction()):
            errors.append(f"Symlink/junction forbidden: {path.relative_to(root)}")
            continue
        if not path.is_file():
            continue
        count += 1
        size = path.stat().st_size
        total += size
        if size > 500_000:
            errors.append(f"File exceeds 500KB: {path.relative_to(root)}")
        try:
            content = path.read_bytes().decode("utf-8")
            if "\x00" in content:
                errors.append(f"Binary NUL in file: {path.relative_to(root)}")
        except UnicodeDecodeError:
            errors.append(f"Not UTF-8 text: {path.relative_to(root)}")
    if count > 50:
        errors.append("More than 50 files.")
    if total > 2_000_000:
        errors.append("Total exceeds 2MB.")
    return {"valid": not errors, "files": count, "bytes": total, "errors": errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", action="version", version=VERSION)
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--source", action="append", required=True)
    p.add_argument("--out", required=True)
    p = sub.add_parser("locate")
    p.add_argument("--corpus", required=True)
    p.add_argument("--quote", required=True)
    p.add_argument("--source-id")
    for command in ("verify", "finalize"):
        p = sub.add_parser(command)
        p.add_argument("--corpus", required=True)
        p.add_argument("--candidate", required=True)
        p.add_argument("--out", required=True)
        if command == "finalize":
            p.add_argument("--case")
    p = sub.add_parser("package-check")
    p.add_argument("--root", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            value = prepare(args.source)
            write_json(args.out, value)
            print(json.dumps({"sources": len(value["sources"]), "statuses": [s["status"] for s in value["sources"]]}))
            return 0 if all(s["status"] == "ready" for s in value["sources"]) else 2
        if args.command == "locate":
            value = locate(read_json(args.corpus), args.quote, args.source_id)
            print(json.dumps(value, ensure_ascii=False, indent=2))
            return 0 if value else 2
        if args.command == "package-check":
            value = package_check(args.root)
        elif args.command == "verify":
            value = verify(read_json(args.corpus), read_json(args.candidate))
            write_json(args.out, value)
        else:
            value = finalize(read_json(args.corpus), read_json(args.candidate), args.out,
                             read_json(args.case) if args.case else None)
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0 if value["valid"] else 2
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"valid": False, "error": f"{type(exc).__name__}: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
