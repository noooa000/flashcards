"""The memory curve. Pure functions -- no database, no clock beyond the date
passed in -- so the scheduling can be reasoned about and asserted on directly.

An SM-2 variant with three grades instead of six, because three buttons is what
the user actually sees. The ease factor carries how well a word has behaved
over time; the interval is what the ease acts on.

Breadth matters more than polish here: the goal is 5,000+ words seen, so a
lapse costs a word its interval but never sends it back behind words that have
not been introduced at all. That policy lives in store.build_queue, not here.
"""

AGAIN, HARD, GOOD = "again", "hard", "good"      # 不认识 / 模糊 / 认识
GRADES = (AGAIN, HARD, GOOD)

EASE_START = 2.5
EASE_MIN = 1.3
EASE_MAX = 2.8
EASE_STEP = {AGAIN: -0.20, HARD: -0.15, GOOD: +0.05}

FIRST_INTERVAL = 1        # days, after the first correct answer
SECOND_INTERVAL = 3
HARD_MULTIPLIER = 1.2
MASTERED_DAYS = 21        # Anki's mature-card threshold; what 掌握 means here


def clamp(value, low, high):
    return max(low, min(high, value))


def schedule(reps, interval, ease, grade):
    """Return the next (reps, interval, ease, lapsed) for one answer.

    reps     consecutive correct answers so far (0 for a new or just-lapsed word)
    interval current spacing in days (0 if not yet scheduled)
    ease     current ease factor
    lapsed   True when the word has to be relearned in this session
    """
    if grade not in GRADES:
        raise ValueError("unknown grade %r" % (grade,))

    ease = clamp(ease + EASE_STEP[grade], EASE_MIN, EASE_MAX)

    if grade == AGAIN:
        return 0, 0, ease, True

    if grade == HARD:
        # Never let 模糊 shrink a schedule -- it is a slower yes, not a no.
        nxt = FIRST_INTERVAL if interval < 1 else max(interval + 1,
                                                      round(interval * HARD_MULTIPLIER))
        return reps + 1, int(nxt), ease, False

    if reps == 0:
        nxt = FIRST_INTERVAL
    elif reps == 1:
        nxt = SECOND_INTERVAL
    else:
        nxt = max(interval + 1, round(interval * ease))
    return reps + 1, int(nxt), ease, False


def is_mastered(interval):
    return interval >= MASTERED_DAYS


if __name__ == "__main__":
    # A word answered 认识 every time must space out, and get there in a
    # sane number of repetitions.
    reps, interval, ease = 0, 0, EASE_START
    seq = []
    for _ in range(7):
        reps, interval, ease, lapsed = schedule(reps, interval, ease, GOOD)
        assert not lapsed
        seq.append(interval)
    assert seq == sorted(seq) and len(set(seq)) == len(seq), seq
    assert is_mastered(seq[-1]), seq
    print("good x7 ->", seq, " ease %.2f" % ease)
    assert next(i for i, v in enumerate(seq) if v >= MASTERED_DAYS) <= 5, seq

    # 不认识 clears the schedule and flags relearning.
    r, i, e, lapsed = schedule(4, 30, 2.5, AGAIN)
    assert (r, i, lapsed) == (0, 0, True), (r, i, lapsed)
    assert e < 2.5
    print("again      -> reps 0, interval 0, ease %.2f, relearn" % e)

    # 模糊 always moves forward, never backward, even from interval 1.
    for start in (0, 1, 2, 10, 100):
        _, nxt, _, lapsed = schedule(2, start, 2.5, HARD)
        assert not lapsed
        assert nxt >= max(1, start), (start, nxt)
    print("hard       -> monotonic from 0/1/2/10/100")

    # Ease stays inside its bounds however long you push it.
    e = EASE_START
    for _ in range(50):
        _, _, e, _ = schedule(1, 5, e, AGAIN)
    assert abs(e - EASE_MIN) < 1e-9, e
    for _ in range(100):
        _, _, e, _ = schedule(1, 5, e, GOOD)
    assert abs(e - EASE_MAX) < 1e-9, e
    print("ease bounds-> [%.1f, %.1f] hold" % (EASE_MIN, EASE_MAX))

    try:
        schedule(0, 0, 2.5, "maybe")
    except ValueError:
        print("unknown grade rejected")
    else:
        raise AssertionError("an unknown grade should not be accepted")

    print("srs: all assertions passed")
