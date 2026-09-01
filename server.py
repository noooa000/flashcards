"""The local server. Bound to 127.0.0.1 only -- nothing here is authenticated,
so it must never be reachable from the network.

Serves three things: the single-page UI, a small JSON API over progress.db, and
mp3s from tts.py. The vocabulary is read once into memory at startup (9k rows,
about 2 MB) and vocab.db is opened read-only, so a bug in this process cannot
damage the extracted dictionary.
"""
import json
import logging
import re
import sqlite3
import threading
import unicodedata
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import store
import srs
import tts

HOST = "127.0.0.1"          # loopback only, deliberately
PORT = 8765

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
VOCAB_DB = HERE.parent / "tcf-tef-vocab" / "vocab.db"
IMAGE_DIR = HERE / "image"          # rewards shown when a goal is met
STICKER_DIR = HERE / "Sticker"      # one overlay sticker per completed extra round
IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
               ".gif": "image/gif", ".webp": "image/webp"}

_vocab = {}                 # entry_id -> dict, loaded once
_vocab_ids = []


def _clean(text):
    """Strip the stray leading punctuation the OCR sometimes left on a gloss
    ('.，使民主化' -> '使民主化')."""
    return re.sub(r"^[\s.,;:·、，。]+", "", text or "")


def _norm(word):
    w = "".join(c for c in unicodedata.normalize("NFD", word)
                if unicodedata.category(c) != "Mn")
    return w.lower().replace("'", "")


MIN_SUSPECT = 13        # a French word this long is rare; a run of glued ones is not


def _garbled(fr, lex, prefixes):
    """True when a sentence still carries the OCR's missing-space damage.

    About 10% of the extracted examples have runs the re-spacer could not split
    ('Ceciestphysiquementimpossible'). Speaking those produces nonsense, so they
    are demoted. A plain length cutoff would also catch real words like
    'traditionnellement', hence the check against the book's own headwords.
    """
    for token in re.findall(r"[A-Za-zÀ-ÿŒœ']+", fr):
        n = _norm(token)
        if len(n) >= MIN_SUSPECT and n not in lex and n[:8] not in prefixes:
            return True
    return False


def list_images():
    """Read the folder each time rather than caching it, so an image dropped in
    while the app is running shows up without a restart."""
    if not IMAGE_DIR.is_dir():
        return []
    return sorted(p.name for p in IMAGE_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_TYPES)


def image_size(path):
    """Return (width, height) by reading only an image header."""
    try:
        with path.open("rb") as fh:
            head = fh.read(32)
            if head.startswith(b"\x89PNG\r\n\x1a\n") and len(head) >= 24:
                return (int.from_bytes(head[16:20], "big"),
                        int.from_bytes(head[20:24], "big"))
            if head[:6] in (b"GIF87a", b"GIF89a") and len(head) >= 10:
                return (int.from_bytes(head[6:8], "little"),
                        int.from_bytes(head[8:10], "little"))
            if head.startswith(b"RIFF") and head[8:12] == b"WEBP":
                chunk = head[12:16]
                if chunk == b"VP8X" and len(head) >= 30:
                    return (int.from_bytes(head[24:27], "little") + 1,
                            int.from_bytes(head[27:30], "little") + 1)
                if chunk == b"VP8L" and len(head) >= 25 and head[20] == 0x2f:
                    bits = int.from_bytes(head[21:25], "little")
                    return ((bits & 0x3fff) + 1, ((bits >> 14) & 0x3fff) + 1)
                if chunk == b"VP8 " and len(head) >= 30 and head[23:26] == b"\x9d\x01\x2a":
                    return (int.from_bytes(head[26:28], "little") & 0x3fff,
                            int.from_bytes(head[28:30], "little") & 0x3fff)
            if not head.startswith(b"\xff\xd8"):
                return None

            fh.seek(2)
            sof = {0xc0, 0xc1, 0xc2, 0xc3, 0xc5, 0xc6, 0xc7,
                   0xc9, 0xca, 0xcb, 0xcd, 0xce, 0xcf}
            while True:
                byte = fh.read(1)
                if not byte:
                    break
                if byte != b"\xff":
                    continue
                marker = fh.read(1)
                while marker == b"\xff":
                    marker = fh.read(1)
                if not marker:
                    break
                code = marker[0]
                if code in (0x01, 0xd8, 0xd9) or 0xd0 <= code <= 0xd7:
                    continue
                raw_length = fh.read(2)
                if len(raw_length) != 2:
                    break
                length = int.from_bytes(raw_length, "big")
                if length < 2:
                    break
                if code in sof:
                    frame = fh.read(5)
                    if len(frame) == 5:
                        return (int.from_bytes(frame[3:5], "big"),
                                int.from_bytes(frame[1:3], "big"))
                    break
                fh.seek(length - 2, 1)
    except OSError:
        return None
    return None


def portrait_images(names):
    """Return image names whose decoded canvas is taller than it is wide."""
    result = []
    for name in names:
        size = image_size(IMAGE_DIR / name)
        if size and size[1] > size[0]:
            result.append(name)
    return result


def list_stickers():
    """Sticker assets are kept separate from reward photos so they cannot be
    selected as the full-size celebration image."""
    if not STICKER_DIR.is_dir():
        return []
    return sorted(p.name for p in STICKER_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in IMAGE_TYPES)


def load_vocab():
    if not VOCAB_DB.exists():
        raise SystemExit("vocabulary not found at %s" % VOCAB_DB)
    con = sqlite3.connect("file:%s?mode=ro" % VOCAB_DB.as_posix(), uri=True)
    con.row_factory = sqlite3.Row

    lex = {_norm(r[0]) for r in con.execute("SELECT lemma FROM entries")}
    prefixes = {w[:8] for w in lex if len(w) >= 8}

    examples = {}
    for r in con.execute("SELECT entry_id, fr, zh FROM examples "
                         "WHERE fr<>'' AND zh<>'' ORDER BY entry_id, idx"):
        examples.setdefault(r["entry_id"], []).append(
            {"fr": r["fr"], "zh": r["zh"], "ok": not _garbled(r["fr"], lex, prefixes)})
    # Clean examples first, so the front of the card and the audio get the best one.
    for v in examples.values():
        v.sort(key=lambda e: not e["ok"])

    for r in con.execute("SELECT id, headword, lemma, variants, ipa, pos, "
                         "definition_zh, mnemonic, associations, distinction "
                         "FROM entries"):
        _vocab[r["id"]] = {
            "id": r["id"], "headword": r["headword"], "lemma": r["lemma"],
            "variants": r["variants"], "ipa": r["ipa"], "pos": r["pos"],
            "definition": _clean(r["definition_zh"]),
            "mnemonic": _clean(r["mnemonic"]),
            "assoc": _clean(r["associations"]), "distinction": _clean(r["distinction"]),
            "examples": examples.get(r["id"], [])[:2],
        }
    con.close()
    _vocab_ids.extend(sorted(_vocab))
    logging.info("loaded %d vocabulary entries", len(_vocab))


class Handler(BaseHTTPRequestHandler):
    server_version = "Flashcards/1.0"

    def log_message(self, fmt, *args):
        logging.debug("%s %s", self.address_string(), fmt % args)

    # ---------------------------------------------------------------- helpers
    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path, ctype):
        try:
            data = path.read_bytes()
        except OSError:
            return self._send(404, {"error": "not found"})
        self._send(200, data, ctype)

    MAX_BODY = 128 * 1024 * 1024      # an import is the only large POST

    def _body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n > self.MAX_BODY:
            raise ValueError("that file is too large (%.0f MB)" % (n / 1e6))
        return json.loads(self.rfile.read(n) or b"{}")

    # ---------------------------------------------------------------- routes
    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        try:
            if u.path in ("/", "/index.html"):
                return self._file(STATIC / "index.html", "text/html; charset=utf-8")
            if u.path == "/api/session":
                return self._send(200, self.session(extra=q.get("extra", ["0"])[0] == "1"))
            if u.path == "/api/stats":
                return self._send(200, self.stats_payload())
            if u.path == "/api/export":
                return self._send(200, store.export(), extra={
                    "Content-Disposition": 'attachment; filename="progress.json"'})
            if u.path == "/api/images":
                images = list_images()
                return self._send(200, {
                    "images": images,
                    "portrait_images": portrait_images(images),
                })
            if u.path == "/api/stickers":
                return self._send(200, {"stickers": list_stickers()})
            if u.path == "/image":
                return self.image(q.get("name", [""])[0])
            if u.path == "/sticker":
                return self.sticker(q.get("name", [""])[0])
            if u.path == "/tts":
                return self.speak(q.get("text", [""])[0])
            return self._send(404, {"error": "no such route"})
        except Exception as exc:
            logging.exception("GET %s failed", u.path)
            return self._send(500, {"error": str(exc)})

    def do_POST(self):
        u = urlparse(self.path)
        try:
            if u.path == "/api/grade":
                return self._send(200, self.do_grade(self._body()))
            if u.path == "/api/celebrate":
                return self._send(200, {"celebrate": store.celebrate_once()})
            if u.path == "/api/extra-complete":
                return self._send(200, self.do_extra_complete(self._body()))
            if u.path == "/api/import":
                return self._send(200, self.do_import(self._body()))
            if u.path == "/api/inspect-import":
                return self._send(200, store.inspect(self._body()))
            return self._send(404, {"error": "no such route"})
        except ValueError as exc:
            return self._send(400, {"error": str(exc)})
        except Exception as exc:
            logging.exception("POST %s failed", u.path)
            return self._send(500, {"error": str(exc)})

    # ---------------------------------------------------------------- actions
    def session(self, extra=False):
        """extra=True is the optional round offered once the day's goal is met."""
        round_day = store.today()
        current_stats = store.stats(len(_vocab), day=round_day)
        round_token = None
        if extra:
            if current_stats["today"] >= current_stats["goal"]:
                ids = store.build_queue(_vocab_ids, day=round_day,
                                        goal=store.EXTRA_SIZE,
                                        min_new=store.EXTRA_NEW, extra=True)
                if ids:
                    round_token = uuid.uuid4().hex
            else:
                ids = []
        else:
            ids = store.build_queue(_vocab_ids, day=round_day)
        return {"queue": [_vocab[i] for i in ids if i in _vocab],
                "extra": extra, "round_token": round_token,
                "round_day": round_day, "stats": current_stats}

    def stats_payload(self):
        s = store.stats(len(_vocab))
        s["history"] = store.history(days=None)
        return s

    def do_grade(self, body):
        entry_id = int(body.get("entry_id", 0))
        if entry_id not in _vocab:
            raise ValueError("unknown entry_id %r" % entry_id)
        token = str(body.get("token") or "")
        if not token:
            raise ValueError("a token is required so a retry cannot count twice")
        result = store.grade(entry_id, str(body.get("grade")), token,
                             revise=bool(body.get("revise")))
        result["stats"] = store.stats(len(_vocab))
        return result

    def do_extra_complete(self, body):
        result = store.complete_extra_round(
            body.get("token"), day=body.get("day"), size=store.EXTRA_SIZE)
        result["stats"] = store.stats(len(_vocab))
        return result

    def do_import(self, body):
        """Restore a previously exported progress file. Replaces what is there,
        after copying the current database aside."""
        result = store.import_progress(body, valid_ids=set(_vocab))
        result["stats"] = store.stats(len(_vocab))
        logging.info("imported %s (backup %s)", result["imported"], result["backup"])
        return result

    def image(self, name):
        # Only ever serve a name that is literally in the folder listing, so no
        # amount of '..' or absolute path in the query can escape it.
        if name not in list_images():
            return self._send(404, {"error": "no such image"})
        path = IMAGE_DIR / name
        self._file(path, IMAGE_TYPES.get(path.suffix.lower(), "application/octet-stream"))

    def sticker(self, name):
        if name not in list_stickers():
            return self._send(404, {"error": "no such sticker"})
        path = STICKER_DIR / name
        self._file(path, IMAGE_TYPES.get(path.suffix.lower(), "application/octet-stream"))

    def speak(self, text):
        text = tts.clean(text)
        if not text:
            return self._send(400, {"error": "nothing to speak"})
        try:
            path = tts.synth(text)
        except Exception as exc:
            # Audio is an enhancement: report it and let the UI carry on silently.
            logging.warning("tts failed for %r: %s", text[:40], exc)
            return self._send(503, {"error": "audio unavailable", "detail": str(exc)})
        self._file(path, "audio/mpeg")


def main(open_browser=True):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    load_vocab()
    store.init()
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    httpd.daemon_threads = True
    url = "http://%s:%d/" % (HOST, PORT)
    logging.info("serving %s  (loopback only)", url)
    if open_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logging.info("stopping")
        httpd.shutdown()


if __name__ == "__main__":
    import sys
    main(open_browser="--no-browser" not in sys.argv)
