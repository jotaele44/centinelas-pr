import hashlib
from pathlib import Path


def test_space_observation_schema_freeze():
    root = Path(__file__).parents[1] / "schemas" / "space_observations"
    expected = {}
    for line in (root / "FROZEN.sha256").read_text().splitlines():
        parts = line.split()
        assert len(parts) == 2, f"invalid freeze row: {line!r}"
        digest, name = parts
        expected[name] = digest
    assert expected
    actual = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in root.glob("*.json")
    }
    assert actual == expected
