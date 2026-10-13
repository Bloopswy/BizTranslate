# Voice Triage

Multilingual voice-message triage with a Streamlit web interface. You record a message in English, Chinese
or Indonesian; it is **transcribed to text**, and then **Google's Gemma model reads the transcript only (never
the audio), detects the language, translates it to English and classifies the tone and urgency**. Business
rules then decide whether a human should ESCALATE, REVIEW, ACCEPT or REJECT each message.

## Problem statement and target users
Staff at hotlines and service counters in multilingual settings (town councils, clinics, eldercare
centres, domestic-worker agencies) receive voice messages in several languages. Urgent, upset
messages get buried because nobody can read them quickly. This tool translates and ranks them so
the most urgent ones are handled first.

## Architecture (4 layers, 100% procedural - no classes)
    Streamlit UI / file -> io_manager -> ai_manager -> logic_manager -> data_manager

| File | Layer | Job |
|---|---|---|
| `io_manager.py` | Input | Every user boundary: terminal `print()`/`input()` **and** all Streamlit widgets; validation; reads input files; speech-to-text (local Whisper); formatting |
| `ai_manager.py` | AI | Builds the prompt from the transcript, calls Gemma, extracts + validates the JSON, retries, never crashes |
| `logic_manager.py` | Logic | Business rules -> ESCALATE / REVIEW / ACCEPT / REJECT + priority score |
| `data_manager.py` | Data | Save/load `data/records.json`, filter, survives missing/corrupt files |
| `app.py` | Wiring | Streamlit entry point (`streamlit run app.py`) |
| `main.py` | Wiring | Terminal entry point (`python main.py` / `--batch`) and the shared `process_record` pipeline |

### Business rules
- **REJECT**: empty translation, or language is not English/Chinese/Indonesian.
- **ESCALATE**: tone is negative **and** urgency >= 4 **and** tone confidence >= 0.7.
- **REVIEW**: language confidence < 0.6, tone confidence < 0.5, or the language chosen by the user
  differs from the language the AI detected.
- **ACCEPT**: everything else.

## Ways to submit a message (tabs in the app)
1. **Record voice** - Streamlit's microphone recorder -> **Transcribe** (local Whisper speech-to-text; choose the
   spoken language or let it auto-detect between English/Chinese/Indonesian) -> the transcript appears in a box
   where you can **fix mistakes** -> **Analyse transcript** sends the text to Gemma.
2. **Browser transcription (HTML)** - `web/recorder.html` embedded in the page (Chrome/Edge speech
   recognition). Add transcripts, download the `.json`, then upload it in tab 4.
3. **Type text** - paste a message, optionally choose its language.
4. **Upload file** - `.json` from the recorder, or `.txt` with one message per line.

Audio never leaves your machine and is never saved or sent to the AI: only the transcript text is sent to
Gemma, and the stored record keeps the transcript, translation, tone, decision and a hash-based id.

## Run it
Get a Google AI Studio key at https://aistudio.google.com/apikey (it works for Gemma; the variable is still called `GEMINI_API_KEY`).

**Locally**
    pip install -r requirements.txt     # includes faster-whisper (speech-to-text)
    export GEMINI_API_KEY=your-key       # Windows PowerShell: $env:GEMINI_API_KEY="your-key"
    streamlit run app.py                 # opens http://localhost:8501

The **first** transcription downloads the Whisper model (about 150 MB for `base`), so it needs internet once;
the Docker image downloads it at build time instead.

Alternatively put `GEMINI_API_KEY=your-key` in a file named `.env` next to `app.py` (copy `.env.example`); it is loaded automatically. If neither is set, the Streamlit app asks for the key in the sidebar.

**Docker**
    docker build -t voice-triage .
    docker run --rm -p 8501:8501 --env-file .env -v "$(pwd)/data:/app/data" voice-triage
    # then open http://localhost:8501

Copy `.env.example` to `.env` first and add your key (the app now reads `.env` automatically, locally and in Docker). The microphone is used by your *browser*, so
recording works with Docker (the container does the transcription). `localhost` counts as a secure origin; for any other address the browser
requires HTTPS before it will allow the microphone.

**Terminal version (still works)**
    python main.py              # interactive menu
    python main.py --batch      # process input/ and exit
    docker run --rm --env-file .env -v "$(pwd)/data:/app/data" -v "$(pwd)/input:/app/input" voice-triage python main.py --batch

**Models** - AI: `gemma-4-26b-a4b-it` by default (set `GEMMA_MODEL=gemma-4-31b-it` for the larger one).
Speech: Whisper `base` by default (set `WHISPER_MODEL=small` for better Chinese/Indonesian accuracy).

**Tests** (no API key, network, Streamlit or Whisper install needed): `python tests/run_tests.py`

## Repeatable output
Record ids are a hash of the language + transcript, the model runs at
temperature 0, and already-processed records are skipped on later runs, so re-running on the same
input gives the same `data/records.json`.
