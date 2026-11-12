import pytest

from app.taxonomy.prompts import render_assessment_prompt


def test_fills_in_the_name():
    template = "Can {{name}} add 43 and 28, and explain how they did it?"
    assert render_assessment_prompt(template, "Mia") == (
        "Can Mia add 43 and 28, and explain how they did it?"
    )


def test_fills_in_every_placeholder_and_trims_the_name():
    template = "When {{name}} shares sweets, does {{name}} give equal groups?"
    assert render_assessment_prompt(template, "  Leo ") == (
        "When Leo shares sweets, does Leo give equal groups?"
    )


def test_keeps_the_possessive_with_a_name():
    assert render_assessment_prompt("Look at {{name}}'s drawing.", "Mia") == (
        "Look at Mia's drawing."
    )


@pytest.mark.parametrize("name", [None, "", "   "])
def test_no_name_falls_back_to_you(name):
    assert render_assessment_prompt("Can {{name}} count to twenty?", name) == (
        "Can you count to twenty?"
    )


@pytest.mark.parametrize(
    ("template", "expected"),
    [
        # Verb after the placeholder agrees with "you".
        ("If {{name}} writes 43 + 28, what happens?", "If you write 43 + 28, what happens?"),
        (
            "When {{name}} is given six cards, what next?",
            "When you are given six cards, what next?",
        ),
        ("If {{name}} has ten counters, what next?", "If you have ten counters, what next?"),
        ("When {{name}} was younger, what happened?", "When you were younger, what happened?"),
        ("If {{name}} doesn't know, what then?", "If you don't know, what then?"),
        ("When {{name}} watches a clock, what next?", "When you watch a clock, what next?"),
        ("If {{name}} carries the ten, what next?", "If you carry the ten, what next?"),
        ("When {{name}} goes shopping, what next?", "When you go shopping, what next?"),
        ("When {{name}} writes, what happens?", "When you write, what happens?"),
        # Past tense and base forms are left alone.
        ("If {{name}} looked at a clock, what next?", "If you looked at a clock, what next?"),
        ("If {{name}} had ten sweets, what next?", "If you had ten sweets, what next?"),
        ("Can {{name}} guess the answer?", "Can you guess the answer?"),
        ("Could {{name}} explain this?", "Could you explain this?"),
        # Words ending in s that are not verbs.
        ("When {{name}} always counts on, what next?", "When you always counts on, what next?"),
        # Verb before the placeholder agrees too.
        ("Does {{name}} know the answer?", "Do you know the answer?"),
        ("Has {{name}} ever seen a prism?", "Have you ever seen a prism?"),
        ("Is {{name}} able to count on?", "Are you able to count on?"),
        ("So, does {{name}} notice it?", "So, do you notice it?"),
        # The verb after an object placeholder is not the child's verb.
        ("Ask {{name}} to count the sides.", "Ask you to count the sides."),
        ("Show {{name}} this shape.", "Show you this shape."),
        # Possessive.
        ("Look at {{name}}'s drawing.", "Look at your drawing."),
        ("{{name}}'s class has 30 pupils.", "Your class has 30 pupils."),
        # Sentence start.
        ("{{name}} writes a sum.", "You write a sum."),
    ],
)
def test_no_name_rewording(template, expected):
    assert render_assessment_prompt(template, None) == expected


def test_no_name_turns_they_and_their_into_you_and_your():
    template = (
        "If {{name}} looked at scores from their class, could they find the mean? "
        "They might use their head."
    )
    assert render_assessment_prompt(template, None) == (
        "If you looked at scores from your class, could you find the mean? You might use your head."
    )


def test_no_name_leaves_them_alone():
    # "them" is the cards here, not the child.
    template = "If {{name}} is given cards, can they lay them out in order?"
    assert render_assessment_prompt(template, None) == (
        "If you are given cards, can you lay them out in order?"
    )


def test_no_name_turns_tell_you_into_say():
    template = "Without adding them up, can {{name}} tell you whether 347 + 129 is odd?"
    assert render_assessment_prompt(template, None) == (
        "Without adding them up, can you say whether 347 + 129 is odd?"
    )
    assert render_assessment_prompt(template, "Mia") == (
        "Without adding them up, can Mia tell you whether 347 + 129 is odd?"
    )


def test_real_prompt_shapes():
    template = (
        "If {{name}} is asked 'which number is closest to 50 — 47 or 54?', "
        "can they use their number knowledge to answer quickly and explain why?"
    )
    assert render_assessment_prompt(template, None) == (
        "If you are asked 'which number is closest to 50 — 47 or 54?', "
        "can you use your number knowledge to answer quickly and explain why?"
    )
    assert render_assessment_prompt(template, "Sam").startswith("If Sam is asked")


def test_template_without_placeholder_is_returned_unchanged():
    assert render_assessment_prompt("Can they count?", None) == "Can they count?"
    assert render_assessment_prompt("Can they count?", "Mia") == "Can they count?"
