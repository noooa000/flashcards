# French Vocabulary Flashcards

A French vocabulary flashcard app built around a database of **9,368 French entries**.

Cards are selected automatically, reviewed according to a spaced-repetition schedule, and read aloud using text-to-speech.

The main goal is **breadth**: see **5,000+ different words** before trying to memorize a small vocabulary perfectly. For that reason, the largest number on the home screen is **Seen / Total**, and daily reviews are never allowed to completely replace new vocabulary.

## Getting Started

Double-click **`Flashcards.bat`**.

On the first launch, the script automatically creates a `.venv` environment and installs `edge-tts`. After that, it starts the local server and opens the app in your browser.

Press **Space** on the home screen to begin.

## Keyboard Controls

| Key                     | Action                                                                                                                                                  |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Space`                 | Go to the next card after flipping / close a checkpoint review / activate the current celebration button / start another set from the completion screen |
| `Esc`                   | Choose “Finish for today” in the celebration dialog                                                                                                     |
| `Ctrl+C`                | I don't know                                                                                                                                            |
| `Backspace`             | Fuzzy                                                                                                                                                   |
| `Delete`                | I know                                                                                                                                                  |
| `Ctrl+C` after flipping | Undo the previous rating and change it to “I don't know”                                                                                                |

If text is selected, `Ctrl+C` still works normally as **Copy** and will not accidentally rate the card.

The equivalent manual startup command is:

```bat
.venv\Scripts\python.exe server.py
```

The server only binds to `127.0.0.1:8765`, so it cannot be accessed by other devices on the local network.

## Daily Scheduling

Each day contains **100 cards**, with **at least 60 unseen words**.

The daily queue is built like this:

1. Reserve 60 slots for new words.
2. Use the remaining 40 slots for reviews due today.
3. If fewer than 40 reviews are due, fill the unused slots with additional new words.
4. Once every word has been seen, the daily session naturally becomes review-only.

This behavior is intentional.

If reviews always had priority, after a few weeks they could consume the entire daily quota of 100 cards. New vocabulary would stop entering the queue, making the goal of seeing 5,000 words much harder to reach.

### Another Set

After completing the daily 100 cards, both the celebration dialog and the completion screen offer **Another Set**.

Each extra set contains **30 new words** and no scheduled reviews. Extra sessions are specifically intended to increase vocabulary coverage.

You can complete multiple extra sets in a row. Words already answered that day will not appear again as new cards.

If there are no unseen words left, the app automatically falls back to due reviews.

When the daily target is reached, the app first shows the final checkpoint review and then opens the celebration card.

After that, every complete 30-word extra set triggers another celebration card.

The same celebration UI is reused with:

* a randomly selected reward image
* an encouragement message
* confetti animation
* **Another Set**
* **Finish for Today**

Extra cards are included in the day's statistics because they are real study activity, so the heatmap may show days with more than 100 completed cards.

The main daily-goal celebration is triggered only once per day. Extra-set celebrations are triggered after every completed 30-word set and do not consume the daily-goal celebration state.

The extra-set configuration is controlled by `EXTRA_SIZE` and `EXTRA_NEW` in `store.py`.

Whenever a full extra set is completed, the app stores the completed set count in the progress database using a unique token. Repeated submissions cannot increase the count twice.

The completion screen selects one sticker from the `Sticker\` directory for each completed extra set and arranges them randomly inside the reward area.

For older progress data that does not contain explicit extra-set records, the app estimates the number of completed sets using:

```text
floor((cards completed today - daily goal) / 30)
```

For display purposes, it uses whichever value is larger: the estimated value or the recorded value. This prevents stickers from disappearing when older progress data is upgraded.

**Each card counts only once per day.**

If you select **I don't know**, the same card will appear again later in the current session. That second appearance is relearning, not additional progress, so it does not increase the daily count.

## Spaced Repetition

The app uses a modified SM-2 system with three ratings.

| Rating       | Key         | Next appearance                                                        |
| ------------ | ----------- | ---------------------------------------------------------------------- |
| I don't know | `Ctrl+C`    | Interval resets, card returns later in the current session, ease −0.20 |
| Fuzzy        | `Backspace` | Interval × 1.2, never shortened, ease −0.15                            |
| I know       | `Delete`    | 1 day → 3 days → × ease, ease +0.05                                    |

Ease is limited to **1.3–2.8**.

A card with an interval of **21 days or more** is considered **mastered**.

If a word is consistently rated **I know**, its approximate intervals are:

```text
1 → 3 → 8 → 22 → 60 → 168 → 470 days
```

This means it reaches the mastered threshold after the fourth successful review.

### Undoing a Rating

Sometimes a word seems familiar on the front, but after seeing the explanation you realize that you rated it too highly.

After flipping the card, press `Ctrl+C` again or click **Undo · I don't know**.

The card will then be rescheduled as **I don't know** and placed back into the current session for relearning.

The undo option is always shown on the back of the card.

If the original rating was already **I don't know**, using the action again simply advances to the next card rather than recording the same rating repeatedly.

After undoing, the app **automatically moves to the next card**. There is no need to press **Next** again because the explanation has already been viewed.

If you press **Next** very quickly yourself, the app still prevents an accidental double skip.

Undoing first reverses the ease adjustment made by the original rating and then applies the **I don't know** calculation.

As a result:

```text
I know → Undo
```

produces the same ease value as choosing:

```text
I don't know
```

from the beginning.

The daily count does not change because the word has already been counted once.

## Checkpoint Reviews

After every **7 unique words**, the app opens a checkpoint review showing those seven words together with their Chinese meanings.

The colored dot on the left represents the latest rating:

* pink = I don't know
* light green = Fuzzy
* olive = I know

Click any row to hear that word again.

Press **Space** or click **Continue** to return to the flashcards.

If fewer than seven words remain at the end of a session, the final partial group is still shown before the completion screen.

The checkpoint counts **unique words**, not card appearances.

A word rated **I don't know** may appear again later in the same session, but it still occupies only one row in the checkpoint review.

The dot always reflects the word's **most recent rating**.

As a result, you may answer more than seven card appearances before accumulating seven unique words for a checkpoint.

Rows rated **Fuzzy** or **I know** also display a small low-contrast French action on the right:

**`Je ne sais pas`**

Clicking it applies the same undo behavior described above:

* changes the rating to **I don't know**
* turns the dot pink
* sends the word back into the current session for relearning

Rows already rated **I don't know** do not display this action.

On the vocabulary screen, the second line of the green record card shows how many unique words remain before the next checkpoint review.

After a checkpoint is completed, the counter resets to 7.

To change the checkpoint interval, edit `REVIEW_EVERY` in:

```text
static\index.html
```

## Study Calendar

The bottom-right corner of the completion screen contains a heatmap calendar for the **current month**.

The calendar:

* starts weeks on Monday
* uses French month and weekday names
* fills successful days with olive
* also fills the current day with olive

Below the calendar are statistics for:

* total successful days
* current streak
* longest streak

## Completion Rewards

When the daily goal is reached, or when an extra set is completed, the celebration dialog randomly selects an image from the **`image\`** directory.

It is paired with an encouragement message, mostly in Chinese with several French sayings mixed in.

The same image is never selected twice in a row.

The final completion screen also contains:

* one random reward image
* one **French saying**
* its Chinese translation

The French sentence is automatically read aloud once.

Click the sentence or the 🔊 button in the top-right corner to hear it again.

The sayings are stored in the `FR_CHEERS` array.

Images are read from the directory **at runtime**.

You can add new files to `image\` at any time and simply refresh the page. Restarting the server is not necessary.

Supported formats:

```text
png
jpg
gif
webp
```

If the directory is empty, the app still works normally. The reward area simply displays the title and saying without an image.

Encouragement messages can be edited or extended in the `FR_CHEERS` array inside:

```text
static\index.html
```

## Interface

The frontend uses an editorial-design-inspired visual style:

* warm off-white paper background
* halftone texture
* thin black outlines
* `14px` hard shadows
* large Georgia serif typography

There are two primary screens:

1. **Vocabulary**
2. **Completion**

The `01 / 02` control in the upper-right corner can also switch between them manually.

### Vocabulary Screen

The upper section contains a large pink flashcard with:

* the French word
* a circular part-of-speech badge
* phonetic transcription

A daily progress card overlaps on the right.

Three answer panels sit immediately below the flashcard:

* cream — **Je ne sais pas / I don't know · 01**
* pink — **C'est flou / Fuzzy · 02**
* olive — **Je connais / I know · 03**

The lower section contains:

* Seen / Total
* progress bar
* month
* streak
* daily target information

After choosing a rating, the flashcard flips and displays:

* definition
* word root / etymological information when available
* example sentences

The bottom controls then change to:

* **Next**
* **Undo**

### Completion Screen

The completion screen contains:

* a kraft-paper panel on the left for **Seen / Goal / Streak**
* an olive reward-image area in the center
* a pink panel containing **Objectif du jour terminé**
* a French saying with Chinese translation
* the monthly heatmap calendar in the bottom-right corner

There are two completion-screen states.

**Daily goal already completed:**
The reward area shows a random image from `image\`.

**Day not started yet:**
The same layout is shown without an image. Instead, the reward area contains placeholder text and a **Start** button.

The circle in the upper-right corner of the reward area displays the cumulative number of days on which the daily goal has been completed.

The interface uses system fonts only:

```text
Georgia
Arial
```

No online font service is required.

The main colors can be edited through the CSS variables near the top of `static\index.html`:

```text
--cream
--pink
--light-green
--olive
--kraft
--ink
```

## Text-to-Speech

French pronunciation is generated using **`edge-tts`**, which provides Microsoft neural voices without requiring an API key.

Current settings:

```text
Voice: fr-FR-DeniseNeural
Rate: -10%
```

The slightly slower speech rate is intended to make shadowing and pronunciation practice easier.

Generated audio is cached in:

```text
data\audio\
```

The cache key is based on:

```text
sha1(voice | rate | text)
```

so identical audio only needs to be generated once.

When the current card is displayed, the app also **prefetches the next card's audio**, reducing delays during continuous study.

On both the front and back of a card, as well as when using the replay button, the app reads:

```text
word → first valid example sentence
```

If TTS generation fails because of a network problem, the card simply remains silent. Study progress is never blocked.

### Pre-caching Audio

To generate audio ahead of time, run:

```bat
.venv\Scripts\python.exe precache.py 500
```

Already cached entries are automatically skipped, so running the command multiple times is inexpensive.

## Example Sentences

Some source example sentences still contain OCR errors where multiple words were accidentally joined together, for example:

```text
Ceciestphysiquementimpossible
```

These suspicious examples are:

* not shown on the front of the card
* not read aloud

Detection is based on unusually long strings that cannot be found in the vocabulary database.

Legitimate long French words such as:

```text
traditionnellement
```

are therefore not automatically rejected simply because they are long.

The affected example sentences are still visible on the back of the card together with their Chinese translations, where they may still be useful for reference.

## Project Structure

```text
server.py             Local HTTP server + read-only vocabulary loading
srs.py                Spaced-repetition logic implemented as pure functions
store.py              progress.db access, daily queues, and statistics
tts.py                edge-tts synthesis + audio cache
precache.py           Offline audio pre-caching utility
static\index.html     Complete frontend
data\progress.db      Learning progress
data\audio\           Cached MP3 files
```

Individual modules can also run their own self-checks:

```bat
.venv\Scripts\python.exe srs.py
.venv\Scripts\python.exe store.py
.venv\Scripts\python.exe tts.py
```

These test:

* spaced-repetition assertions
* queue generation
* idempotency
* celebration state
* streak calculations
* TTS synthesis and concurrent-request deduplication

## Data Safety

The vocabulary database is always opened in **read-only mode** (`mode=ro`), so the flashcard application cannot modify or corrupt the source vocabulary data.

Learning progress is stored separately in:

```text
data\progress.db
```

The vocabulary data and progress data are therefore independent.

The footer provides two backup controls:

* **Export Progress** — downloads a JSON backup
* **Import Progress** — restores progress from a backup

Every rating request contains a one-time token, so accidental double-clicks or network retries cannot increase the daily count twice.

### Importing Progress

Importing is a **replacement operation**, not a merge.

It is designed as the counterpart to exporting, primarily for:

* moving progress to another machine
* restoring progress after accidental deletion

After selecting an import file, the app first displays a confirmation dialog comparing the imported data with the current progress.

The dialog includes information such as:

* number of words
* number of records
* export time
* current progress statistics

Nothing is written until the import is confirmed.

Before replacing the current database, the app automatically creates a backup:

```text
data\progress-before-import-<timestamp>.db
```

If the wrong file is imported, the previous database can therefore be restored by replacing `progress.db` with the backup.

Every imported value is validated for both type and allowed range before being written to the database.

Words that no longer exist in the vocabulary database are skipped and reported in the import result.

Files that do not match the expected export format are rejected **before the progress database is modified**.

## Configuration

| File        | Constant                   | Purpose                                                                            |
| ----------- | -------------------------- | ---------------------------------------------------------------------------------- |
| `store.py`  | `DAILY_GOAL`               | Total number of daily cards. Default: 100                                          |
| `store.py`  | `MIN_NEW`                  | Minimum number of new cards. Default: 60                                           |
| `store.py`  | `EXTRA_SIZE` / `EXTRA_NEW` | Size and new-word count of an extra set. Default: 30 / 30                          |
| `srs.py`    | `MASTERED_DAYS`            | Interval required for a card to count as mastered. Default: 21 days                |
| `srs.py`    | `EASE_STEP`                | Ease adjustments for the three ratings                                             |
| `tts.py`    | `VOICE` / `RATE`           | TTS voice and speech rate                                                          |
| `server.py` | `PORT`                     | Local server port. Default: 8765                                                   |
| `server.py` | `MIN_SUSPECT`              | Minimum word length used when detecting suspicious OCR concatenations. Default: 13 |

## Known Limitations

* `edge-tts` requires an internet connection for audio that has not already been cached. Cached words continue to work offline.
* Phonetic transcriptions come from OCR data, so nasal vowels and other symbols may occasionally be incomplete or incorrect.
* Roughly 3% of vocabulary entries do not have a successfully parsed part of speech. In those cases, the original part-of-speech text remains at the beginning of the Chinese definition.
* The audio cache grows as more vocabulary is synthesized. It can be deleted safely; missing audio will simply be generated again when needed.

