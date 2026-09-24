import json
import sys
from pathlib import Path

from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]

# 契约模型已并入 backend/app/schemas/v04/（单一来源，不再保留独立副本）
sys.path.insert(0, str(ROOT / "backend"))

from app.schemas.v04.models import (  # noqa: E402
    MODEL_REGISTRY,
    IncompleteProfileError,
    TripProfileDraft,
    finalize_trip_profile,
)


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_valid_fixtures() -> int:
    count = 0
    for path in sorted((ROOT / "fixtures" / "valid").glob("*.json")):
        payload = load(path)
        model = MODEL_REGISTRY[payload["model"]]
        model.model_validate(payload["data"])
        print(f"PASS valid: {path.name}")
        count += 1
    return count


def validate_invalid_fixtures() -> int:
    count = 0
    for path in sorted((ROOT / "fixtures" / "invalid").glob("*.json")):
        payload = load(path)
        model = MODEL_REGISTRY[payload["model"]]
        try:
            model.model_validate(payload["data"])
        except ValidationError:
            print(f"PASS invalid: {path.name}")
            count += 1
            continue
        raise AssertionError(f"Invalid fixture unexpectedly passed: {path.name}")
    return count


def validate_business_cases() -> int:
    count = 0
    for path in sorted((ROOT / "fixtures" / "business").glob("*.json")):
        payload = load(path)
        if payload["case"] == "locked_node_immutability":
            violation = any(
                payload["before_nodes"].get(node_id)
                != payload["after_nodes"].get(node_id)
                for node_id in payload["locked_node_ids"]
            )
            if violation != payload["expect_violation"]:
                raise AssertionError(f"Unexpected locked-node result: {path.name}")
            print(f"PASS business: {path.name}")
            count += 1
            continue
        if payload["case"] == "draft_finalize_success":
            draft = TripProfileDraft.model_validate(payload["draft"])
            actual_missing = draft.compute_missing_fields()
            if actual_missing != payload["expect_missing_before"]:
                raise AssertionError(
                    f"Unexpected missing fields before finalize: {path.name} "
                    f"-> {actual_missing}"
                )
            profile = finalize_trip_profile(draft)
            for field, expected in payload["expect"].items():
                actual = getattr(profile, field)
                if hasattr(actual, "model_dump"):
                    actual = actual.model_dump()
                if actual != expected:
                    raise AssertionError(
                        f"Finalized {field} mismatch in {path.name}: {actual} != {expected}"
                    )
            print(f"PASS business: {path.name}")
            count += 1
            continue
        if payload["case"] == "draft_finalize_failure":
            draft = TripProfileDraft.model_validate(payload["draft"])
            actual_missing = draft.compute_missing_fields()
            if actual_missing != payload["expect_missing_fields"]:
                raise AssertionError(
                    f"Unexpected missing fields in {path.name}: {actual_missing}"
                )
            try:
                finalize_trip_profile(draft)
            except IncompleteProfileError as error:
                if error.missing_fields != payload["expect_missing_fields"]:
                    raise AssertionError(
                        f"IncompleteProfileError fields mismatch: {path.name}"
                    ) from error
                print(f"PASS business: {path.name}")
                count += 1
                continue
            raise AssertionError(
                f"Incomplete draft unexpectedly finalized: {path.name}"
            )
        raise AssertionError(f"Unknown business fixture case: {path.name}")
    return count


if __name__ == "__main__":
    valid = validate_valid_fixtures()
    invalid = validate_invalid_fixtures()
    business = validate_business_cases()
    print(
        f"Validated {valid} valid, {invalid} invalid, "
        f"and {business} business fixtures"
    )
