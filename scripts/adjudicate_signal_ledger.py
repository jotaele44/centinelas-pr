#!/usr/bin/env python3
"""Reclassify a frozen signal ledger with bound, model-assisted evidence.

This stage never polls or downloads.  It consumes an immutable acquisition
snapshot, scores every row twice with a locally installed ONNX NLI model, and
writes a derived ledger, full decision ledger, and classification receipt.
"""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from centinelas.classify.adjudication import (  # noqa: E402
    MUTABLE_CLASSIFICATION_FIELDS,
    NLI_LABEL_DESCRIPTIONS,
    adjudicate_signal,
    immutable_projection,
    signal_text,
)
from centinelas.classify.labels import DomainLabel  # noqa: E402

MODEL_REPOSITORY = "MoritzLaurer/multilingual-MiniLMv2-L6-mnli-xnli"
MODEL_REVISION = "0a71e92a985b6e1ad1828cf67ce9c459639c1dca"
MODEL_FILES: dict[str, tuple[int, str]] = {
    "config.json": (
        921,
        "e08b628c4d46c8601dda34ddb40a7857e5961870b80482382d420db6dfb6e00e",
    ),
    "model.onnx": (
        428_127_016,
        "79f8cda2b1230585a95ea0514a6f1bd21c5c986ba0529bb3261213a3e195fa6e",
    ),
    "sentencepiece.bpe.model": (
        5_069_051,
        "cfc8146abe2a0488e9e2a0c56de7952f7c11ab059eca145a0a727afce0db2865",
    ),
    "special_tokens_map.json": (
        964,
        "8c785abebea9ae3257b61681b4e6fd8365ceafde980c21970d001e834cf10835",
    ),
    "tokenizer.json": (
        17_082_854,
        "b2116c05e7305eea30394284760789681c5b3440dd4cd9a8c77539da68f9e8a6",
    ),
    "tokenizer_config.json": (
        1_255,
        "10dd51e1952b6725b3c65edd16411a4ffe97a6f61636f11a7505bcb0bdb6b360",
    ),
}
ALGORITHM_VERSION = "centinelas-evidence-adjudication-v1"
ALLOWED_BASE_METHODS = {
    "keyword_fast_path",
    "llm",
    "keyword_fallback",
    "unclassified_fallback",
}


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def json_bytes(value: Any, *, pretty: bool = False) -> bytes:
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return text.encode("utf-8")


def jsonl_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n" for row in rows
    )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} is not a JSON object")
            rows.append(value)
    return rows


def write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def git_head() -> str | None:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def validate_model(model_dir: Path) -> list[dict[str, Any]]:
    actual_names = {path.name for path in model_dir.iterdir() if path.is_file()}
    if actual_names != set(MODEL_FILES):
        raise ValueError(
            "model directory file set mismatch: "
            f"expected={sorted(MODEL_FILES)}, actual={sorted(actual_names)}"
        )
    manifest = []
    for name, (expected_bytes, expected_hash) in MODEL_FILES.items():
        path = model_dir / name
        actual_bytes = path.stat().st_size
        actual_hash = sha256_path(path)
        if (actual_bytes, actual_hash) != (expected_bytes, expected_hash):
            raise ValueError(
                f"model binding mismatch for {name}: "
                f"expected=({expected_bytes}, {expected_hash}), "
                f"actual=({actual_bytes}, {actual_hash})"
            )
        manifest.append(
            {
                "name": name,
                "path": str(path),
                "bytes": actual_bytes,
                "sha256": actual_hash,
            }
        )
    return manifest


def validate_base_snapshot(
    *,
    ledger_path: Path,
    rows: list[dict[str, Any]],
    receipt: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if receipt.get("schema_version") != "1.0.0":
        errors.append("base receipt schema_version must be 1.0.0")
    if receipt.get("repository") != "jotaele44/centinelas-pr":
        errors.append("base receipt names the wrong repository")
    if receipt.get("classification") != "PROVISIONAL":
        errors.append("base receipt must preserve the provisional acquisition result")

    ledger = receipt.get("ledger")
    if not isinstance(ledger, dict):
        errors.append("base receipt is missing ledger metadata")
    else:
        if ledger.get("sha256") != sha256_path(ledger_path):
            errors.append("base ledger SHA256 does not match its receipt")
        if ledger.get("rows") != len(rows):
            errors.append("base ledger row count does not match its receipt")
        method_counts = dict(
            sorted(Counter(str(row.get("classification_method")) for row in rows).items())
        )
        if ledger.get("classification_method_counts") != method_counts:
            errors.append("base classification-method counts do not match")
        if ledger.get("polled_items_before_limit") != len(rows):
            errors.append("base snapshot does not retain every polled item")

    ids = [row.get("signal_id") for row in rows]
    if any(not isinstance(value, str) or not value for value in ids):
        errors.append("base ledger has missing signal IDs")
    elif len(ids) != len(set(ids)):
        errors.append("base ledger has duplicate signal IDs")
    if any(row.get("is_synthetic") is not False for row in rows):
        errors.append("base ledger contains synthetic or untyped rows")
    if any(row.get("classification_method") not in ALLOWED_BASE_METHODS for row in rows):
        errors.append("base ledger contains an unsupported classification method")

    gates = receipt.get("gates")
    if not isinstance(gates, dict):
        errors.append("base receipt gates are missing")
    else:
        failed_except_classifier = sorted(
            key
            for key, value in gates.items()
            if key != "no_classifier_fallback" and value is not True
        )
        if failed_except_classifier:
            errors.append(
                f"base receipt has non-classifier gate failures: {failed_except_classifier}"
            )
        if gates.get("no_classifier_fallback") is not False:
            errors.append("base receipt does not isolate classifier fallback as its open gate")
    return errors


def load_source_families(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"source_id", "source_family"}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("source registry is missing source_id or source_family")
        rows = list(reader)
    source_ids = [row["source_id"] for row in rows]
    if any(not value for value in source_ids) or len(source_ids) != len(set(source_ids)):
        raise ValueError("source registry IDs are missing or duplicated")
    return {row["source_id"]: row["source_family"] for row in rows}


class OnnxNliClassifier:
    """Small local NLI scorer with no network or generative decoding path."""

    def __init__(self, model_dir: Path, *, threads: int) -> None:
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import numpy as np
        import onnxruntime as ort
        from transformers import AutoTokenizer

        options = ort.SessionOptions()
        options.intra_op_num_threads = threads
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        self._np = np
        self._tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True)
        self._session = ort.InferenceSession(
            str(model_dir / "model.onnx"),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._input_names = {item.name for item in self._session.get_inputs()}
        config = json.loads((model_dir / "config.json").read_text(encoding="utf-8"))
        if config.get("label2id", {}).get("entailment") != 0:
            raise ValueError("model entailment label is not bound to output index 0")

    def score(
        self,
        texts: list[str],
        *,
        batch_rows: int,
    ) -> list[dict[DomainLabel, float]]:
        label_order = list(NLI_LABEL_DESCRIPTIONS)
        results: list[dict[DomainLabel, float]] = []
        for start in range(0, len(texts), batch_rows):
            batch = texts[start : start + batch_rows]
            premises: list[str] = []
            hypotheses: list[str] = []
            for text in batch:
                for description in NLI_LABEL_DESCRIPTIONS.values():
                    premises.append(text)
                    hypotheses.append(f"This text is about {description}.")
            encoded = self._tokenizer(
                premises,
                hypotheses,
                padding=True,
                truncation=True,
                max_length=384,
                return_tensors="np",
            )
            feeds = {
                name: encoded[name].astype(self._np.int64)
                for name in self._input_names
                if name in encoded
            }
            logits = self._session.run(None, feeds)[0][:, 0]
            logits = logits.reshape(len(batch), len(label_order))
            shifted = logits - logits.max(axis=1, keepdims=True)
            probabilities = self._np.exp(shifted)
            probabilities /= probabilities.sum(axis=1, keepdims=True)
            for row_scores in probabilities:
                results.append(
                    {
                        label: round(float(row_scores[index]), 8)
                        for index, label in enumerate(label_order)
                    }
                )
        return results


def equivalence_counts(
    base_rows: list[dict[str, Any]],
    derived_rows: list[dict[str, Any]],
) -> dict[str, int]:
    before = {
        (str(row.get("signal_id")), str(label))
        for row in base_rows
        for label in row.get("labels", [])
    }
    after = {
        (str(row.get("signal_id")), str(label))
        for row in derived_rows
        for label in row.get("labels", [])
    }
    return {
        "intersection": len(before & after),
        "a_only": len(before - after),
        "b_only": len(after - before),
        "union": len(before | after),
        "symmetric_difference": len(before ^ after),
    }


def runtime_manifest() -> dict[str, Any]:
    packages = {
        distribution.metadata["Name"]: distribution.version
        for distribution in importlib.metadata.distributions()
        if distribution.metadata["Name"]
    }
    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "packages": dict(sorted(packages.items(), key=lambda item: item[0].lower())),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-ledger", required=True)
    parser.add_argument("--base-receipt", required=True)
    parser.add_argument(
        "--source-registry", default=str(REPO_ROOT / "data/reference/source_registry.csv")
    )
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--out-ledger", required=True)
    parser.add_argument("--out-decisions", required=True)
    parser.add_argument("--out-receipt", required=True)
    parser.add_argument("--batch-rows", type=int, default=16)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--require-pass", action="store_true")
    args = parser.parse_args(argv)

    if args.batch_rows <= 0 or args.threads <= 0:
        parser.error("--batch-rows and --threads must be greater than zero")

    base_ledger = Path(args.base_ledger).resolve()
    base_receipt_path = Path(args.base_receipt).resolve()
    source_registry = Path(args.source_registry).resolve()
    model_dir = Path(args.model_dir).resolve()
    out_ledger = Path(args.out_ledger).resolve()
    out_decisions = Path(args.out_decisions).resolve()
    out_receipt = Path(args.out_receipt).resolve()
    outputs = (out_ledger, out_decisions, out_receipt)
    if any(path.exists() for path in outputs):
        print("FAIL - output paths already exist; refusing to overwrite evidence")
        return 2

    rows = load_jsonl(base_ledger)
    base_receipt = json.loads(base_receipt_path.read_text(encoding="utf-8"))
    base_errors = validate_base_snapshot(
        ledger_path=base_ledger,
        rows=rows,
        receipt=base_receipt,
    )
    if base_errors:
        print("FAIL - base snapshot validation failed: " + "; ".join(base_errors))
        return 2

    model_files = validate_model(model_dir)
    source_families = load_source_families(source_registry)
    missing_sources = sorted(
        {str(row.get("source_id")) for row in rows if row.get("source_id") not in source_families}
    )
    if missing_sources:
        print(f"FAIL - ledger source IDs are absent from the registry: {missing_sources}")
        return 2

    classifier = OnnxNliClassifier(model_dir, threads=args.threads)
    texts = [signal_text(row) for row in rows]
    first_scores = classifier.score(texts, batch_rows=args.batch_rows)
    second_scores = classifier.score(texts, batch_rows=args.batch_rows)
    deterministic_scores = first_scores == second_scores

    derived_rows: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    for row, scores in zip(rows, first_scores, strict=True):
        derived, decision = adjudicate_signal(
            row,
            source_family=source_families[str(row["source_id"])],
            nli_scores=scores,
        )
        derived_rows.append(derived)
        decisions.append(decision)

    base_ids = [row["signal_id"] for row in rows]
    derived_ids = [row["signal_id"] for row in derived_rows]
    decision_ids = [row["signal_id"] for row in decisions]
    unresolved_count = sum(row["state"] == "UNRESOLVED" for row in decisions)
    immutable_rows_preserved = all(
        immutable_projection(before) == immutable_projection(after)
        for before, after in zip(rows, derived_rows, strict=True)
    )
    method_counts = dict(
        sorted(Counter(str(row.get("classification_method")) for row in derived_rows).items())
    )
    label_counts = dict(
        sorted(Counter(label for row in derived_rows for label in row["labels"]).items())
    )

    ledger_content = jsonl_bytes(derived_rows)
    decisions_content = jsonl_bytes(decisions)
    gates = copy.deepcopy(base_receipt["gates"])
    gates.update(
        {
            "no_classifier_fallback": unresolved_count == 0
            and set(method_counts) == {"model_assisted_adjudication"},
            "exact_base_ledger_binding": base_receipt["ledger"]["sha256"]
            == sha256_path(base_ledger),
            "exact_base_receipt_binding": True,
            "model_files_bound": len(model_files) == len(MODEL_FILES),
            "complete_decision_coverage": base_ids == decision_ids == derived_ids,
            "unique_decision_ids": len(decision_ids) == len(set(decision_ids)),
            "two_pass_score_determinism": deterministic_scores,
            "row_conservation": len(rows) == len(derived_rows) == len(decisions),
            "immutable_fields_preserved": immutable_rows_preserved,
            "terminal_decisions": unresolved_count == 0,
            "zero_unresolved_decisions": unresolved_count == 0,
        }
    )

    receipt = copy.deepcopy(base_receipt)
    receipt.update(
        {
            "schema_version": "1.1.0",
            "classification": "PASS" if all(gates.values()) else "PROVISIONAL",
            "classification_repository_head": git_head(),
            "classification_completed_at": datetime.now(timezone.utc).isoformat(),
            "gates": gates,
        }
    )
    receipt["ledger"] = {
        **receipt["ledger"],
        "path": str(out_ledger),
        "sha256": sha256_bytes(ledger_content),
        "rows": len(derived_rows),
        "synthetic_rows": sum(bool(row.get("is_synthetic")) for row in derived_rows),
        "duplicate_signal_ids": len(derived_ids) - len(set(derived_ids)),
        "classification_method_counts": method_counts,
    }
    algorithm = {
        "name": ALGORITHM_VERSION,
        "mutable_fields": sorted(MUTABLE_CLASSIFICATION_FIELDS),
        "label_descriptions": {
            label.value: description for label, description in NLI_LABEL_DESCRIPTIONS.items()
        },
        "acceptance_support_total": 3,
        "review_support_total": 2,
        "nli_strong": {"score": 0.55, "top_two_margin": 0.25},
        "nli_moderate": {"score": 0.35, "top_two_margin": 0.10},
        "inference": {
            "provider": "CPUExecutionProvider",
            "batch_rows": args.batch_rows,
            "threads": args.threads,
            "max_length": 384,
            "score_decimal_places": 8,
            "passes": 2,
        },
    }
    receipt["classification_overlay"] = {
        "base_ledger": {
            "path": str(base_ledger),
            "bytes": base_ledger.stat().st_size,
            "sha256": sha256_path(base_ledger),
            "rows": len(rows),
        },
        "base_receipt": {
            "path": str(base_receipt_path),
            "bytes": base_receipt_path.stat().st_size,
            "sha256": sha256_path(base_receipt_path),
        },
        "source_registry": {
            "path": str(source_registry),
            "bytes": source_registry.stat().st_size,
            "sha256": sha256_path(source_registry),
        },
        "model": {
            "repository": MODEL_REPOSITORY,
            "revision": MODEL_REVISION,
            "directory": str(model_dir),
            "files": model_files,
        },
        "runtime": runtime_manifest(),
        "algorithm": {
            **algorithm,
            "sha256": sha256_bytes(json_bytes(algorithm)),
        },
        "decisions": {
            "path": str(out_decisions),
            "bytes": len(decisions_content),
            "sha256": sha256_bytes(decisions_content),
            "rows": len(decisions),
            "state_counts": dict(sorted(Counter(row["state"] for row in decisions).items())),
            "unresolved": unresolved_count,
        },
        "derived_label_counts": label_counts,
        "classification_method_counts": method_counts,
        "original_to_derived_label_equivalence": equivalence_counts(rows, derived_rows),
        "two_pass_score_vectors_sha256": [
            sha256_bytes(
                json_bytes(
                    [{label.value: value for label, value in row.items()} for row in score_pass]
                )
            )
            for score_pass in (first_scores, second_scores)
        ],
        "invariants": {
            "input_rows": len(rows),
            "derived_rows": len(derived_rows),
            "decision_rows": len(decisions),
            "ordered_signal_ids_equal": base_ids == decision_ids == derived_ids,
            "immutable_fields_preserved": immutable_rows_preserved,
            "unresolved_decisions": unresolved_count,
        },
    }

    write_bytes_atomic(out_ledger, ledger_content)
    write_bytes_atomic(out_decisions, decisions_content)
    write_bytes_atomic(out_receipt, json_bytes(receipt, pretty=True))

    if receipt["classification"] == "PASS":
        from federation_export import _production_receipt_errors

        exporter_errors = _production_receipt_errors(
            receipt,
            ledger_path=out_ledger,
            signals=derived_rows,
        )
    else:
        exporter_errors = ["not evaluated because classification overlay is provisional"]
    receipt["gates"]["production_export_guard"] = not exporter_errors
    receipt["classification_overlay"]["exporter_validation_errors"] = exporter_errors
    receipt["classification"] = "PASS" if all(receipt["gates"].values()) else "PROVISIONAL"
    write_bytes_atomic(out_receipt, json_bytes(receipt, pretty=True))

    print(
        f"wrote {out_ledger}, {out_decisions}, and {out_receipt} - "
        f"rows={len(rows)}, unresolved={unresolved_count}, "
        f"classification={receipt['classification']}, methods={method_counts}, "
        f"labels={label_counts}"
    )
    if args.require_pass and receipt["classification"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
