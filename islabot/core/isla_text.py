from __future__ import annotations
import re

ADDRESS_WORDS = [
    "simps", "simp",
    "pups", "pup", "puppies", "puppy",
    "dogs", "dog",
    "pets", "pet",
    "kittens", "kitten"
]

# Patterns like "Good morning, pups" -> "Good morning pups"
_COMMA_AFTER_ADDRESS = re.compile(rf"\b({'|'.join(ADDRESS_WORDS)})\b\s*,", re.IGNORECASE)
_COMMA_BEFORE_ADDRESS = re.compile(rf",\s*\b({'|'.join(ADDRESS_WORDS)})\b", re.IGNORECASE)

# Fix cases like:
# "Good morning,\npups" -> "Good morning pups"
_SPLIT_ADDRESS_ACROSS_LINES = re.compile(
    rf"(\b(?:good morning|morning|hey|hi)\b)\s*,?\s*\n\s*\b({'|'.join(ADDRESS_WORDS)})\b",
    re.IGNORECASE
)

# Also fix: "Good morning,\n simps" etc.
_SPLIT_ADDRESS_GENERIC = re.compile(
    rf",?\s*\n\s*\b({'|'.join(ADDRESS_WORDS)})\b",
    re.IGNORECASE
)

def sanitize_isla_text(text: str) -> str:
    """
    Enforces global tone rules:
    - Never use commas when referencing simps/pups/pets/dogs/etc (in direct address phrases).
    - Never split the address phrase across lines.
    - Light cleanup of spacing.
    """
    if not text:
        return text

    t = text

    # 1) Fix "Good morning,\npups" -> "Good morning pups"
    t = _SPLIT_ADDRESS_ACROSS_LINES.sub(r"\1 \2", t)

    # 2) Fix ",\n pups" etc -> " pups" (rare)
    # (only when it immediately precedes an address word)
    t = _SPLIT_ADDRESS_GENERIC.sub(lambda m: " " + m.group(1), t)

    # 3) Remove comma before/after address word
    # "pups, ..." -> "pups ..."
    t = _COMMA_AFTER_ADDRESS.sub(lambda m: m.group(1), t)
    # "..., pups" -> "... pups"
    t = _COMMA_BEFORE_ADDRESS.sub(lambda m: " " + m.group(1), t)

    # 4) Normalize a few common awkward punctuation combos
    t = t.replace(" ,", " ")
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()

