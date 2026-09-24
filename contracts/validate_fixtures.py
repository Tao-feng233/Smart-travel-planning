import json
from pathlib import Path

from pydantic import ValidationError

from contract_models import MODEL_REGISTRY


ROOT = Path(__file__).resolve().parents[1]


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
