"""Reading and checking the os-taxonomy files, before anything touches the database."""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOPICS_FILE = "topics.json"
DEPENDENCIES_FILE = "dependencies.json"
RESEARCH_FILE = "teaching-research.json"
CLUSTERS_FILE = "clusters.json"
MANIFEST_FILE = "manifest.json"

# The only data files the importer opens. curriculum-standards.json and the
# other upstream files are deliberately never read (restrictive source terms).
DATA_FILES = (TOPICS_FILE, DEPENDENCIES_FILE, RESEARCH_FILE, CLUSTERS_FILE)


class TaxonomyError(Exception):
    """The source data cannot be imported."""


class ChecksumError(TaxonomyError):
    """A file does not match the checksum recorded for it."""


class CycleError(TaxonomyError):
    """The prerequisite graph has a cycle."""


@dataclass(frozen=True)
class TaxonomySourceData:
    taxonomy_version: str
    research_schema_version: int
    checksums: dict[str, str]
    topics: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    research_records: list[dict[str, Any]]
    clusters: list[dict[str, Any]]


def read_checkout_commit(taxonomy_path: Path) -> str | None:
    """The commit a checkout is at, read from .git without running git.

    None if the folder is not a git checkout.
    """
    git_dir = taxonomy_path / ".git"
    head_file = git_dir / "HEAD"
    if not head_file.is_file():
        return None
    head = head_file.read_text(encoding="utf-8").strip()
    if not head.startswith("ref:"):
        return head
    ref = head.removeprefix("ref:").strip()
    ref_file = git_dir / ref
    if ref_file.is_file():
        return ref_file.read_text(encoding="utf-8").strip()
    packed = git_dir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            sha, _, name = line.partition(" ")
            if name == ref:
                return sha
    return None


def load_source(taxonomy_path: Path) -> TaxonomySourceData:
    """Read the data files, verifying every checksum first. Raises ChecksumError on any mismatch."""
    data_dir = taxonomy_path / "data"
    manifest_path = data_dir / MANIFEST_FILE
    if not manifest_path.is_file():
        raise TaxonomyError(
            f"No taxonomy found at {taxonomy_path} (missing data/{MANIFEST_FILE}). "
            "Run scripts/fetch_taxonomy first."
        )
    manifest = json.loads(manifest_path.read_bytes())
    listed = manifest.get("files", {})

    raw: dict[str, bytes] = {}
    checksums: dict[str, str] = {}
    for name in DATA_FILES:
        path = data_dir / name
        if not path.is_file():
            raise TaxonomyError(f"Missing data file: {path}")
        expected = (listed.get(name) or {}).get("sha256")
        if not expected:
            raise ChecksumError(f"{MANIFEST_FILE} lists no SHA-256 for {name}")
        raw[name] = path.read_bytes()
        actual = hashlib.sha256(raw[name]).hexdigest()
        if actual != expected:
            raise ChecksumError(
                f"SHA-256 mismatch for {name}: {MANIFEST_FILE} says {expected}, file is {actual}"
            )
        checksums[name] = actual

    research = json.loads(raw[RESEARCH_FILE])
    if research.get("topicFileSha256") != checksums[TOPICS_FILE]:
        raise ChecksumError(
            f"{RESEARCH_FILE} was exported for a different {TOPICS_FILE}: "
            f"topicFileSha256 is {research.get('topicFileSha256')}, "
            f"{TOPICS_FILE} is {checksums[TOPICS_FILE]}"
        )

    topics = json.loads(raw[TOPICS_FILE])
    return TaxonomySourceData(
        taxonomy_version=str(topics["version"]),
        research_schema_version=int(research["schemaVersion"]),
        checksums=checksums,
        topics=topics["topics"],
        dependencies=json.loads(raw[DEPENDENCIES_FILE])["dependencies"],
        research_records=research["records"],
        clusters=json.loads(raw[CLUSTERS_FILE])["clusters"],
    )
