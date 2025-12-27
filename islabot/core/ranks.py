from __future__ import annotations

RANKS = [
    ("Stray", 0, 500),
    ("Worthless Pup", 500, 1000),
    ("Leashed Pup", 1000, 5000),
    ("Collared Dog", 5000, 10000),
    ("Trained Pet", 10000, 15000),
    ("Devoted Dog", 15000, 20000),
    ("Cherished Pet", 20000, 50000),
    ("Favorite Puppy", 50000, 10**18),
]

def rank_from_lce(lce: int) -> str:
    for name, lo, hi in RANKS:
        if lo <= lce < hi:
            return name
    return "Stray"

