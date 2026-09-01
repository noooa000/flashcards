"""Warm the audio cache ahead of time.

Studying works fine without this -- the server synthesises on demand and the UI
prefetches one card ahead -- but on a slow connection the first play of each
new word costs about a second. Run this while you are away and those become
instant.

    .venv\\Scripts\\python.exe precache.py 500

Only words you have not seen yet are considered, in the order the session
builder would introduce them. Already-cached lines are skipped, so re-running
it is cheap.
"""
import sys
import time

import server
import store
import tts


def main(limit):
    server.load_vocab()
    store.init()
    ids = store.build_queue(server._vocab_ids, goal=limit, min_new=limit)
    if not ids:
        print("nothing pending -- the daily goal is already met")
        return

    lines = []
    for i in ids:
        e = server._vocab[i]
        lines.append(tts.clean(e["headword"].lstrip("*").split(",")[0].split("(")[0]))
        ex = e["examples"][0] if e["examples"] else None
        if ex and ex["ok"]:
            lines.append(tts.clean(ex["fr"]))

    todo = [t for t in dict.fromkeys(lines) if t and not tts.cached(t)]
    print("%d cards -> %d lines, %d already cached, %d to fetch"
          % (len(ids), len(lines), len(lines) - len(todo), len(todo)))

    t0 = time.time()
    done = failed = 0
    for n, text in enumerate(todo, 1):
        try:
            tts.synth(text)
            done += 1
        except Exception as exc:
            failed += 1
            print("  ! %s -- %s" % (text[:38], exc))
        if n % 25 == 0 or n == len(todo):
            rate = n / max(time.time() - t0, 1e-6)
            print("  %d/%d  %.1f/s  eta %.0fs" % (n, len(todo), rate, (len(todo) - n) / rate))
    print("cached %d, failed %d, in %.0fs" % (done, failed, time.time() - t0))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
