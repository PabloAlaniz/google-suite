"""The API image prunes googleapiclient's discovery documents: keep the list in sync."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD_CALL = re.compile(r'\bbuild\(\s*"([a-z0-9]+)",\s*"(v[0-9.]+)"')


def _kept() -> set[str]:
    dockerfile = (ROOT / "api" / "Dockerfile").read_text()
    match = re.search(r'ARG DISCOVERY_KEEP="([^"]+)"', dockerfile)
    assert match, "DISCOVERY_KEEP not found in api/Dockerfile"
    return set(match.group(1).split())


def _used() -> set[str]:
    sources = [*ROOT.glob("packages/*/src/**/*.py"), *ROOT.glob("api/src/**/*.py")]
    sources += ROOT.glob("cli/src/**/*.py")
    return {
        f"{name}.{version}"
        for path in sources
        for name, version in BUILD_CALL.findall(path.read_text())
    }


def test_every_built_api_keeps_its_discovery_document():
    used = _used()
    assert {"gmail.v1", "sheets.v4", "oauth2.v2"} <= used  # the scan finds the calls
    assert used <= _kept(), f"add to DISCOVERY_KEEP: {sorted(used - _kept())}"


def test_kept_documents_exist_in_googleapiclient():
    import googleapiclient

    documents = Path(googleapiclient.__file__).parent / "discovery_cache" / "documents"
    missing = [doc for doc in _kept() if not (documents / f"{doc}.json").exists()]
    assert not missing
