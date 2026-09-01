"""Edge TTS -> cached mp3. French, for the flashcard app.

Same caching scheme as B:\\Code\\Spinish\\tts.py -- sha1 of (voice|rate|text),
written to a .part file first so a half-downloaded mp3 can never become
cache-visible. Playback is the browser's job here, so there is no Qt player.

The one addition over the Spinish version is in-flight de-duplication: the UI
prefetches the next card while the current one plays, so two requests for the
same text can easily overlap. Without the lock below both would call the
service and both would write the same file.
"""
import asyncio
import hashlib
import logging
import threading
from pathlib import Path

VOICE = "fr-FR-DeniseNeural"
RATE = "-10%"                 # a touch under native speed, for shadowing

AUDIO_DIR = Path(__file__).resolve().parent / "data" / "audio"

# key -> Event. A thread that finds a key already present waits on its event
# instead of starting a second synthesis. Guarded by _inflight_lock.
_inflight = {}
_inflight_lock = threading.Lock()


def clean(text):
    """Collapse whitespace before synthesis, so one cache entry serves the same
    line however it happened to be wrapped."""
    return " ".join(str(text).split())


def cache_key(text):
    return hashlib.sha1(("%s|%s|%s" % (VOICE, RATE, clean(text))).encode("utf-8")).hexdigest()


def audio_path(text):
    return AUDIO_DIR / (cache_key(text) + ".mp3")


def cached(text):
    p = audio_path(text)
    return p if p.exists() and p.stat().st_size > 0 else None


def _synthesise(text, path):
    import edge_tts

    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")

    async def run():
        await edge_tts.Communicate(text, VOICE, rate=RATE).save(str(tmp))

    asyncio.run(run())
    if not tmp.exists() or tmp.stat().st_size == 0:
        raise RuntimeError("edge-tts produced no audio for %r" % text[:40])
    tmp.replace(path)          # only now is it visible to the cache


def synth(text):
    """Blocking. Returns the mp3 path, generating it only if not already cached.

    Concurrent callers asking for the same text: the first synthesises, the
    rest wait for it and then use the same file.
    """
    text = clean(text)
    if not text:
        raise ValueError("nothing to speak")
    path = audio_path(text)
    if path.exists() and path.stat().st_size > 0:
        return path

    key = path.name
    with _inflight_lock:
        event = _inflight.get(key)
        mine = event is None
        if mine:
            event = threading.Event()
            _inflight[key] = event

    if not mine:                       # someone else is already on it
        event.wait(timeout=60)
        if path.exists() and path.stat().st_size > 0:
            return path
        raise RuntimeError("the synthesis we waited on did not produce a file")

    try:
        _synthesise(text, path)
        return path
    finally:
        with _inflight_lock:
            _inflight.pop(key, None)
        event.set()                    # release the waiters either way


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    line = "Je n'ai fait que l'apercevoir et il disparut."
    print("voice:", VOICE, " rate:", RATE)
    print("cached before:", cached(line))
    p = synth(line)
    print("wrote:", p, "(%d bytes)" % p.stat().st_size)
    print("second call is a cache hit:", synth(line) == p)

    # two threads, one text: exactly one synthesis
    other = "Bonjour, ceci est un test de prononciation."
    if cached(other):
        cached(other).unlink()
    results = []
    threads = [threading.Thread(target=lambda: results.append(synth(other)))
               for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print("3 concurrent requests ->", len(set(results)), "distinct file(s), all exist:",
          all(r.exists() for r in results))
