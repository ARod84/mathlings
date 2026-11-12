"""The pinned version of the os-taxonomy dataset, and what we say about it.

TAXONOMY_COMMIT is the single place the pin lives. The fetch scripts read it
from this file, and the importer refuses a vendor checkout at any other commit.
Upgrading the dataset is a deliberate edit of this constant, never "latest".
"""

TAXONOMY_REPO_URL = "https://github.com/withmarbleapp/os-taxonomy.git"

# Reviewed version, dated 2026-11-11.
TAXONOMY_COMMIT = "ce4eb95df6d0675762daef4d2318f9e545e73d98"

# Counts taken when the pinned commit was reviewed. The importer prints its own
# counts next to these; a difference means the pin or the scope rules changed.
REVIEWED_COUNTS = {
    "topics_in_scope": 561,
    "topics_total": 688,
    "closure_non_math": 116,
}

ATTRIBUTION = (
    "Contains data from the Marble Skill Taxonomy (withmarble.com), "
    "licensed under ODbL 1.0 and CC BY-SA 4.0."
)

# Import scope: mathematics topics whose age range overlaps these ages.
SCOPE_SUBJECT = "Mathematics"
SCOPE_AGE_MIN = 7
SCOPE_AGE_MAX = 12
