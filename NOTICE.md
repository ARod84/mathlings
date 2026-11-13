# Notice

## Marble Skill Taxonomy (os-taxonomy)

> Contains data from the Marble Skill Taxonomy (withmarble.com), licensed under ODbL 1.0 and CC BY-SA 4.0.

Mathlings uses the open dataset [os-taxonomy](https://github.com/withmarbleapp/os-taxonomy), the
Marble Skill Taxonomy, © Generative Spark, Inc. (Marble), <https://withmarble.com>.

**Pinned version:** commit `ce4eb95df6d0675762daef4d2318f9e545e73d98` (dated 2026-11-11). The pin
is the `TAXONOMY_COMMIT` constant in `backend/app/taxonomy/constants.py`.

### What we use

The dataset is not stored in this repository. `backend/scripts/fetch_taxonomy` downloads it into
`backend/vendor/os-taxonomy/` (gitignored), and the importer copies a subset into our own database:

- **Topics:** mathematics topics for ages 7–12, plus every topic they depend on through
  prerequisites (some younger, some from other subjects). Fields: id, type, subject, domain, name,
  description, evidence, assessment prompt, age range and centrality.
- **Prerequisite edges** between those topics, with strength and reason.
- **Teaching research** for those topics (pedagogy, learning activities, assessment, sources and
  confidence), including the error patterns, which we also store as a table of their own.
- **Cluster summaries** for the subjects and domains of those topics.

### What we do not use

`data/curriculum-standards.json`, `data/curriculum-alignments.json` and the `standards` field of
each topic are never read or imported. Some of the upstream curriculum sources (Common Core, IB
and others) have restrictive terms.

### Licenses

| Part of the dataset                                                                  | License                                                                                                       |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| The database: the collection, its structure, ids and relationships                   | [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/)                            |
| The text: names, descriptions, evidence, prompts, reasons, summaries, research prose | [Creative Commons Attribution-ShareAlike 4.0 (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/) |

The upstream license texts are in the dataset's own repository:
[LICENSE](https://github.com/withmarbleapp/os-taxonomy/blob/ce4eb95df6d0675762daef4d2318f9e545e73d98/LICENSE)
and
[LICENSE-CONTENT](https://github.com/withmarbleapp/os-taxonomy/blob/ce4eb95df6d0675762daef4d2318f9e545e73d98/LICENSE-CONTENT).

### What the licenses ask of us

- **Attribution.** Wherever taxonomy content is shown, the app displays the attribution line at the
  top of this section. The same text is stored in the `taxonomy_source` table, so the frontend can
  read it from the database.
- **Share-alike.** Using the dataset inside the app is allowed. If we ever publish a modified
  version of the dataset itself (for example an export of our database tables), that version must
  be offered under the same terms: ODbL 1.0 for the database and CC BY-SA 4.0 for the text.

This file is a summary for people working on the project, not legal advice.
