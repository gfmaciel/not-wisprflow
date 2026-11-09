"""Overlap de-duplication is conditional and conservative."""

import pytest

from transcript_merge import append_transcript


@pytest.mark.parametrize("old,new,expected", [
    ("because the presentation", "the presentation needs to be ready",
     "because the presentation needs to be ready"),
    ("A gente precisa de algo", "de algo que funcione",
     "A gente precisa de algo que funcione"),
    ("Hello, world!", "hello world! Again.", "Hello, world! Again."),
    ("Please do this", "do this", "Please do this"),
    ("bom dia", "Bom dia novamente", "bom dia novamente"),
])
def test_duplicate_boundary_words_are_removed(old, new, expected):
    assert append_transcript(old, new, True) == expected


def test_natural_pause_never_removes_repetition():
    assert append_transcript("bom dia", "bom dia outra vez") == "bom dia bom dia outra vez"


def test_one_shared_word_is_not_enough_to_drop_content():
    assert append_transcript("eu acho", "acho que sim", True) == "eu acho acho que sim"


def test_empty_and_unrelated_transcripts():
    assert append_transcript("", "Oi!", True) == "Oi!"
    assert append_transcript("Oi!", "", True) == "Oi!"
    assert append_transcript("começou", "terminou", True) == "começou terminou"


def test_repeated_words_in_a_different_location_are_preserved():
    assert append_transcript("que que acontece", "é isso que que eu digo", True) == (
        "que que acontece é isso que que eu digo"
    )
