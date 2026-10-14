# Meeting Translator

A live interpreter for a **business meeting between two parties** who speak **English, Indonesian or Chinese**.
Each sentence is spoken (or typed), transcribed to text, and **Google's Gemma model reads the text only (never
the audio), translates it into the other party's language and reads its tone**. The screen always shows the
**latest translation plus the 3 sentences before it, each with a timestamp**.

## Problem statement and target users
Business partners who do not share a language (a Singapore supplier and an Indonesian distributor, an
English-speaking team and a Chinese client...) either hire an interpreter or lose time and trust in
misunderstandings. This tool gives both sides an instant translation they can read, keeps a short running
record of what was just said, and warns when a moment is tense or a translation is uncertain, so
people can slow down and confirm before a misunderstanding costs a deal.

## Architecture (4 layers, 100% procedural - no classes)
    voice / text / file -> io_manager -> ai_manager -> logic_manager -> data_manager

| File | Layer | Job |
|---|---|---|
| `io_manager.py` | Input | Every user boundary: terminal `print()`/`input()` **and** all Streamlit widgets; meeting setup; validation; reading meeting files; speech-to-text (local Whisper); timestamps; formatting |
| `ai_manager.py` | AI | Builds the prompt from the sentence **plus the previous 3 sentences as context**, calls Gemma, extracts + validates the JSON, retries, never crashes |
| `logic_manager.py` | Logic | Business rules -> TENSION / CHECK / ACCEPT / REJECT |
| `data_manager.py` | Data | Save/load `data/records.json`, per-meeting history, last-N sentences, filtering, survives missing/corrupt files |
| `app.py` | Wiring | Streamlit entry point (`streamlit run app.py`) |
| `main.py` | Wiring | Terminal entry point and the shared `process_record` pipeline |

### What the AI returns for every sentence (validated JSON)
`detected_language`, `language_confidence`, `translation`, `translation_confidence`, `tone`, `tone_confidence`,
`intensity` (1-5) and `tone_reason`. The translation and the tone note are written in the **listener's** language.

### Business rules
- **REJECT**: empty translation, or the sentence is not English, Indonesian or Chinese.
- **TENSION**: tone is angry, frustrated or anxious **and** intensity >= 4 **and** tone confidence >= 0.7.
  The app suggests slowing down and confirming that both sides understand.
- **CHECK**: language confidence < 0.6, translation confidence < 0.6, or the speaker used a different
  language than the one set for that party (probably the wrong speaker or a bad transcription).
  The app suggests confirming with the speaker. (A sentence can be TENSION and also list these doubts.)
- **ACCEPT**: everything else.

## Using the web app (`streamlit run app.py`)
**Sidebar - Meeting setup:** meeting name, a *Start a new meeting* button, and for **Party A** and **Party B** a
name and a language (English / Indonesian / Chinese), plus the **time zone** used for timestamps
(*Auto* uses your browser's zone). Sentences with the same meeting name belong together.

**Live tab**
1. Choose **who is speaking**.
2. Give the sentence: **Record voice** (record -> *Transcribe* -> fix the text if needed -> *Translate*),
   **Type text**, **Upload meeting file**, or **Browser transcription (HTML)**.
   Voice is transcribed in the speaker's own language, so Whisper is told which one to expect.
3. The **latest translation** appears large, with the original, the tone and any TENSION/CHECK warning, and below
   it the **previous 3 sentences** (what was said, the translation, tone, and a **timestamp** for each).

**Transcript tab:** the whole meeting in order with timestamps, summary counts, and downloads
(minutes `.txt`, `.json`, `.csv`). You can switch to earlier meetings.

**Filter tab:** pick any of **Tone**, **Language spoken**, **Translated into** and **Speaker**. Leave a box empty to
ignore it. If more than one box is filled in, choose **All of them (AND)** or **Any of them (OR)**; inside one box the
choices are always OR. "More filters" narrows by meeting and flag. Matches can be downloaded.

## Meeting file formats (for the *Upload meeting file* tab and `input/`)
JSON object (sets the parties too):

    {"meeting": "supply-negotiation",
     "parties": {"A": {"name": "Acme Foods", "language": "English"},
                 "B": {"name": "Mitra Pangan", "language": "Indonesian"}},
     "utterances": [{"speaker": "A", "timestamp": "2026-10-14T09:00:05+08:00", "transcript": "Good morning."},
                    {"speaker": "B", "timestamp": "2026-10-14T09:00:21+08:00", "transcript": "Selamat pagi."}]}

A plain JSON list of utterances also works (parties come from the sidebar / command line). Text files use one
sentence per line, optionally with a timestamp:

    A: Good morning
    [2026-10-14T09:00:21+08:00] B: Selamat pagi

Two examples are in `input/`. Timestamps are optional in files (shown as `--:--:--`); live sentences are stamped with
the time they were submitted.

## Run it
Get a Google AI Studio key at https://aistudio.google.com/apikey (it works for Gemma; the variable is still called
`GEMINI_API_KEY`).

**Locally**
    pip install -r requirements.txt     # includes faster-whisper (speech-to-text)
    export GEMINI_API_KEY=your-key       # Windows PowerShell: $env:GEMINI_API_KEY="your-key"
    streamlit run app.py                 # opens http://localhost:8501

Alternatively put `GEMINI_API_KEY=your-key` in a file named `.env` next to `app.py` (copy `.env.example`); it is
loaded automatically. If neither is set, the app asks for the key in the sidebar.
The **first** transcription downloads the Whisper model (about 150 MB for `base`), so it needs internet once; the
Docker image downloads it at build time instead.

**Docker**
    docker build -t meeting-translator .
    docker run --rm -p 8501:8501 --env-file .env -v "$(pwd)/data:/app/data" meeting-translator
    # then open http://localhost:8501

The microphone is used by your *browser*, so recording works with Docker (the container does the transcription).
`localhost` counts as a secure origin; for any other address the browser requires HTTPS before it allows the microphone.

**Terminal version**
    python main.py                       # menu: say a sentence, show latest + previous 3, transcript, filter, setup...
    python main.py --batch               # translate every file in input/ (each file is its own meeting) and exit
    python main.py --meeting standup --a-name Acme --a-language English --b-name Mitra --b-language Indonesian
    docker run --rm --env-file .env -v "$(pwd)/data:/app/data" meeting-translator python main.py --batch

(The terminal prints times in the computer's own time zone; inside Docker that is UTC.)

**Models** - AI: `gemma-4-26b-a4b-it` by default (set `GEMMA_MODEL=gemma-4-31b-it` for the larger one).
Speech: Whisper `base` by default (set `WHISPER_MODEL=small` for better Chinese/Indonesian accuracy).

**Tests** (no API key, network, Streamlit or Whisper install needed): `python tests/run_tests.py`

## Repeatable output
Sentence ids are a hash of meeting + time + speaker + text (+ line number for files), the model runs at temperature 0,
and a sentence that is already stored is skipped, so re-reading the same file gives the same `data/records.json`.
The same words said twice in a meeting are two separate sentences.

## Notes
- Audio never leaves your machine and is never saved or sent to the AI: only text is sent to Gemma.
- Records from the earlier triage version still load (they appear under the meeting "earlier-records").
