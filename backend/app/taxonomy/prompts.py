"""Rendering of upstream assessment prompts.

The prompts are written about the child in the third person, for example
"If {{name}} writes 43 + 28, can they explain their method?". With a name the
placeholder is simply filled in. Without one the prompt is turned to face the
reader: "If you write 43 + 28, can you explain your method?".
"""

import re

PLACEHOLDER = "{{name}}"

# Verbs before the placeholder: "Does {{name}} know" -> "Do you know".
_AUX_BEFORE = {"does": "do", "has": "have", "is": "are", "was": "were"}

# Verbs after the placeholder that do not follow the plain "drop the s" rule.
_VERB_AFTER = {
    "is": "are",
    "isn't": "aren't",
    "was": "were",
    "wasn't": "weren't",
    "has": "have",
    "hasn't": "haven't",
    "does": "do",
    "doesn't": "don't",
    "goes": "go",
}

# Words ending in "s" that can follow the placeholder and are not verbs.
_NOT_VERBS = {
    "always",
    "sometimes",
    "perhaps",
    "this",
    "his",
    "its",
    "thus",
    "plus",
    "across",
    "unless",
    "towards",
    "afterwards",
    "besides",
    "as",
    "us",
    "themselves",
}

# After these words the placeholder is not the subject of a present-tense
# verb ("can {{name}} work", "ask {{name}} to"), so the next word is left alone.
_NO_AGREEMENT_AFTER = {
    "can",
    "could",
    "would",
    "should",
    "will",
    "might",
    "may",
    "must",
    "does",
    "do",
    "did",
    "has",
    "is",
    "was",
    "ask",
    "asks",
    "asked",
    "show",
    "shows",
    "showed",
    "give",
    "gives",
    "gave",
    "tell",
    "tells",
    "told",
    "telling",
    "let",
    "help",
    "to",
    "with",
    "for",
    "of",
    "at",
    "in",
    "by",
    "from",
}

# Singular "they" for the child becomes "you". "them" is left alone: in these
# prompts it nearly always means the things being counted or sorted.
_PRONOUNS = {
    "they": "you",
    "they're": "you're",
    "they've": "you've",
    "they'd": "you'd",
    "they'll": "you'll",
    "their": "your",
    "theirs": "yours",
    "themselves": "yourself",
}

# \u2019 is the typographic apostrophe, which the upstream text also uses.
_WORD = r"[A-Za-z]+(?:['\u2019][A-Za-z]+)?"
_NAME_RE = re.compile(
    rf"(?:(?P<before>{_WORD})(?P<gap>\s+))?"
    rf"\{{\{{name\}}\}}(?P<possessive>['\u2019]s)?"
    rf"(?:(?P<gap2>\s+)(?P<after>{_WORD}))?"
)
_PRONOUN_RE = re.compile(r"\b(" + "|".join(_PRONOUNS) + r")\b", re.IGNORECASE)


# The prompts say "can {{name}} tell you whether...", where "you" is the adult
# listening. Once the child is "you", that becomes "can you say whether...".
_TELL_YOU_RE = re.compile(r"\btell you\b")


def _match_case(replacement: str, original: str) -> str:
    return replacement.capitalize() if original[:1].isupper() else replacement


def _second_person_verb(word: str) -> str:
    """'writes' -> 'write'. Past-tense and other words come back unchanged."""
    lower = word.lower().replace("\u2019", "'")
    if lower in _VERB_AFTER:
        return _match_case(_VERB_AFTER[lower], word)
    if lower in _NOT_VERBS or not lower.endswith("s") or lower.endswith(("ss", "us", "is")):
        return word
    if lower.endswith("ies") and len(lower) > 4:
        return word[:-3] + "y"
    if lower.endswith(("sses", "shes", "ches", "xes", "zzes", "oes")):
        return word[:-2]
    return word[:-1]


def _to_second_person(match: re.Match[str]) -> str:
    before, gap = match.group("before"), match.group("gap") or ""
    after, gap2 = match.group("after"), match.group("gap2") or ""
    possessive = match.group("possessive")

    out = ""
    before_key = (before or "").lower()
    if before:
        agreed = _AUX_BEFORE.get(before_key)
        out = (_match_case(agreed, before) if agreed else before) + gap

    at_start = match.start() == 0 and not before
    you = "your" if possessive else "you"
    out += you.capitalize() if at_start else you

    if after:
        is_subject = not possessive and before_key not in _NO_AGREEMENT_AFTER
        out += gap2 + (_second_person_verb(after) if is_subject else after)
    return out


def render_assessment_prompt(template: str, name: str | None) -> str:
    """Fill the {{name}} placeholder of an upstream assessment prompt.

    With a name, every placeholder becomes that name. Without one (None or
    blank), the prompt is reworded to address the reader as "you": verbs next
    to the placeholder are made to agree ("{{name}} writes" -> "you write",
    "Does {{name}}" -> "Do you"), "{{name}}'s" becomes "your", they/their become
    you/your, and "tell you" becomes "say".

    Known limit: a prompt that already speaks to an adult as "you" ("If you
    show {{name}} some cards") reads oddly without a name. Such prompts are rare.
    """
    cleaned = (name or "").strip()
    if cleaned:
        return template.replace(PLACEHOLDER, cleaned)
    if PLACEHOLDER not in template:
        return template

    text = _TELL_YOU_RE.sub("say", template)
    text = _NAME_RE.sub(_to_second_person, text)
    return _PRONOUN_RE.sub(lambda m: _match_case(_PRONOUNS[m.group(1).lower()], m.group(1)), text)
