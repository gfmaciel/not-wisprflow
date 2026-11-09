"""Conservative text de-duplication for audio windows that actually overlap."""

from __future__ import annotations

import re

_WORD = re.compile(r"\\S+")
_EDGE_PUNCTUATION = re.compile(r"^\\W+|\\W+$", re.UNICODE)
MAX_MATCH_WORDS = 12


def _normal(word: str) -> str:
    return _EDGE_PUNCTUATION.sub("", word).casefold()


def append_transcript(previous: str, current: str, overlaps_previous: bool = False) -> str:
    """Join adjacent transcripts, removing a shared suffix/prefix of >=2 words.

    No fuzzy guessing: ASR changes around a boundary are preferable to
    accidentally deleting real speech. Only call with overlaps_previous=True
    when the second audio segment includes the first segment's audio tail.
    """
    previous, current = previous.strip(), current.strip()
    if not previous:
        return current
    if not current:
        return previous
    if overlaps_previous:
        prior = list(_WORD.finditer(previous))
        fresh = list(_WORD.finditer(current))
        limit = min(MAX_MATCH_WORDS, len(prior), len(fresh))
        for count in range(limit, 1, -1):
            left = [_normal(m.group()) for m in prior[-count:]]
            right = [_normal(m.group()) for m in fresh[:count]]
            if all(left) and left == right:
                if count == len(fresh):
                    return previous
                current = current[fresh[count].start():].lstrip()
                break
    return previous + " " + current if current else previous
