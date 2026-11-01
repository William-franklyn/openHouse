"""Card representation and hand evaluation for Texas Hold'em - pure
functions, no engine/state knowledge, so the evaluator itself can be
tested in total isolation from betting logic.

A card is a 2-character string: rank + suit, e.g. "Ah" (Ace of hearts),
"Td" (Ten of diamonds), "2s" (Two of spades) - chosen over an (int, int)
tuple because it's exactly what the frontend wants to render with zero
translation, and because the JSON-serialized engine state is this same
string already, so there's no encode/decode step at the display boundary.
"""

import itertools
import random

RANKS = "23456789TJQKA"
SUITS = "cdhs"

HIGH_CARD, PAIR, TWO_PAIR, TRIPS, STRAIGHT, FLUSH, FULL_HOUSE, QUADS, STRAIGHT_FLUSH = range(9)

HAND_CATEGORY_NAMES = {
    HIGH_CARD: "High Card",
    PAIR: "Pair",
    TWO_PAIR: "Two Pair",
    TRIPS: "Three of a Kind",
    STRAIGHT: "Straight",
    FLUSH: "Flush",
    FULL_HOUSE: "Full House",
    QUADS: "Four of a Kind",
    STRAIGHT_FLUSH: "Straight Flush",
}


def build_deck() -> list[str]:
    return [r + s for r in RANKS for s in SUITS]


def shuffled_deck() -> list[str]:
    deck = build_deck()
    random.shuffle(deck)
    return deck


def _rank_value(card: str) -> int:
    return RANKS.index(card[0]) + 2


def _suit(card: str) -> str:
    return card[1]


def evaluate_5(cards: list[str]) -> tuple:
    """Returns a tuple (category, [tiebreak values, highest first]) for
    EXACTLY 5 cards - directly comparable via Python tuple comparison
    (bigger tuple = better hand), the standard trick for this problem."""
    values = sorted((_rank_value(c) for c in cards), reverse=True)
    suits = [_suit(c) for c in cards]
    is_flush = len(set(suits)) == 1

    distinct = sorted(set(values), reverse=True)
    is_straight = False
    straight_high = None
    if len(distinct) == 5:
        if distinct[0] - distinct[4] == 4:
            is_straight = True
            straight_high = distinct[0]
        elif distinct == [14, 5, 4, 3, 2]:  # the wheel - Ace plays low
            is_straight = True
            straight_high = 5

    if is_straight and is_flush:
        return (STRAIGHT_FLUSH, [straight_high])

    counts: dict[int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    # Sort by (count desc, value desc) so quads/trips/pairs outrank kickers
    # of the same count, and ties within a count break by rank.
    by_count = sorted(counts.items(), key=lambda kv: (-kv[1], -kv[0]))
    counts_desc = [c for _, c in by_count]
    ranks_by_group = [v for v, _ in by_count]

    if counts_desc[0] == 4:
        return (QUADS, ranks_by_group)
    if counts_desc[0] == 3 and counts_desc[1] == 2:
        return (FULL_HOUSE, ranks_by_group)
    if is_flush:
        return (FLUSH, values)
    if is_straight:
        return (STRAIGHT, [straight_high])
    if counts_desc[0] == 3:
        return (TRIPS, ranks_by_group)
    if counts_desc[0] == 2 and counts_desc[1] == 2:
        return (TWO_PAIR, ranks_by_group)
    if counts_desc[0] == 2:
        return (PAIR, ranks_by_group)
    return (HIGH_CARD, values)


def best_hand(cards: list[str]) -> tuple:
    """Best 5-card hand value out of any number (>=5) of cards - for
    Hold'em this is always called with exactly 7 (2 hole + 5 community).
    Checks all C(n,5) combinations; 21 for n=7, cheap enough to brute-force
    rather than writing a smarter incremental evaluator."""
    return max(evaluate_5(list(combo)) for combo in itertools.combinations(cards, 5))


def hand_description(value: tuple) -> str:
    return HAND_CATEGORY_NAMES[value[0]]
