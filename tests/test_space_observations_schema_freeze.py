import hashlib
from pathlib import Path


def test_space_observation_schema_freeze():
    root = Path(__file__).parents[1] / "schemas" / "space_observations"
    expected = {}
    for line in (root / "FROZEN.sha256").read_text().splitlines():
        digest, name = line.split("  ", 1)
        expected[name] = digest
    assert expected
    for name, digest in expected.items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest
