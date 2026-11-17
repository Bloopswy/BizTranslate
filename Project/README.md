# Meeting Translator (OOP edition – Phase 2)

A live interpreter for a **business meeting between two parties** who speak English, Indonesian or Chinese.
Each sentence (typed, **spoken**, or read from a meeting file) is sent as **text** to Google's Gemma model, which translates it
for the other party and reads its tone. Business rules then flag tense moments (**TENSION**), doubtful
translations (**CHECK**), unusable output (**REJECT**) or routine sentences (**ACCEPT**).

Four managers (unchanged responsibilities from Phase 1), now object-oriented:
`IOManager → AIManager → LogicManager → DataManager`. See [EXPLANATION.md](EXPLANATION.md) for the design,
OOP/SOLID mapping and new-feature notes, and [docs/DESIGN_DIAGRAMS.md](docs/DESIGN_DIAGRAMS.md) for UML / data flow.

## Run it

You need a Gemini API key (https://aistudio.google.com/apikey). **Never commit it** – `.env` is git-ignored.

### With Docker (recommended – nothing else to install)
```bash
docker build -t meeting-translator .
# (the speech-to-text model is downloaded into the image while building; add --build-arg PRELOAD_WHISPER=0
#  to skip that: faster build, and the model then downloads on first use instead)

# web GUI at http://localhost:8501 (records/reports kept in ./data)
docker run --rm -p 8501:8501 -e GEMINI_API_KEY=your-key -v "$(pwd)/data:/app/data" meeting-translator

# terminal app
docker run -it --rm -e GEMINI_API_KEY=your-key -v "$(pwd)/data:/app/data" meeting-translator python main.py
docker run -it --rm -e GEMINI_API_KEY=your-key -v "$(pwd)/data:/app/data" meeting-translator python main.py --batch

# run the automated tests (no key, no network)
docker run --rm meeting-translator python -m unittest discover -s tests -t .
```
(PowerShell: use `${PWD}/data` instead of `$(pwd)/data`.)

### Without Docker (Python 3.10+)
```bash
pip install -r requirements.txt
cp .env.example .env            # then put your key in .env
streamlit run app.py            # web GUI (threaded, live progress)
python main.py                  # terminal menu
python main.py --batch          # process input/*.json and input/*.txt
python main.py --meeting standup --a-name Acme --a-language English --b-name Mitra --b-language Indonesian
python -m unittest discover -s tests -t .
```
Voice input needs `faster-whisper` (in `requirements.txt`); the first transcription downloads the speech model
(about 150 MB for `base`), so it needs internet once.

## Web GUI (advanced deliverable) and threading (advanced deliverable)
`streamlit run app.py` – sidebar sets the meeting, the two parties and the time zone. **Live** tab: type a sentence, record your
voice, or upload a meeting file; translations are processed on a **background worker thread**, so the page stays responsive and a
progress bar (with a Cancel button) updates live. The latest translation and the previous 5 sentences (configurable in `config/rules.json`)
are shown with timestamps, tone metrics, and TENSION/CHECK warnings. **Transcript & report** tab: outcome metrics, tone &
language bar charts, meeting report, transcript, and downloads (`.txt/.json/.csv`). **Filter** tab: tone / language /
translated-into / speaker with AND/OR.


## Voice input (speech-to-text)
* **Web GUI (continuous conversation):** Live tab → *Record voice* → check **Continuous conversation (hands-free)** → click **Start conversation**. The browser listens continuously using Web Audio VAD, slices each sentence when you pause, auto-detects the speaker's language (scoped to Party A / Party B), and queues translation automatically.
* **Web GUI (push-to-talk):** Live tab → *Record voice* (with **Continuous conversation** unchecked): keep **Auto-detect speaker from spoken language** checked (or uncheck to force the selected speaker) → record → **Transcribe** → fix any mistakes in the box → **Translate transcript**. The browser asks for microphone permission (works on `localhost` and `https`).
* **Terminal:** menu **10** → pick the speaker (`A`, `B`, or **3) Auto-detect from voice**) → give the path of an audio file (`.wav .mp3 .m4a .ogg .flac .webm .mp4 .aac`) → Enter accepts what was heard, type a corrected sentence to replace it, or `/cancel`.
* **How it works:** Whisper (through `faster-whisper`, on the CPU) turns the recording into text **on this computer**;
  only that text is sent to Gemma. The audio is never stored and never sent to the AI.
* **Accuracy:** speak one sentence at a time in a quiet place, and check names and numbers in the transcript box before
  translating. `WHISPER_MODEL=small` is more accurate for Chinese and Indonesian (but slower).

## Menu
1 type a sentence · 2 process meeting files · 3 latest sentence + previous 3 · 4 transcript · 5 filter ·
6 summary · **7 meeting report (new)** · 8 meeting setup · 9 quit · **10 say a sentence from a voice recording
(audio file, speech-to-text)**

## Configuration
| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | – (required) | API key |
| `GEMMA_MODEL` | `gemma-4-26b-a4b-it` | model name |
| `WHISPER_MODEL` | `base` | speech-to-text size: `tiny` / `base` / `small` / `medium` (bigger = more accurate, slower) |
| `DATA_FILE` | `data/records.json` | records; a `.csv` name switches to CSV storage |
| `RULES_FILE` | `config/rules.json` | tunable thresholds (see file) |
| `INPUT_DIR` / `REPORT_DIR` / `LOG_FILE` | `input` / `data/reports` / `data/app.log` | folders and log |

## Meeting file formats (`input/`)
JSON object `{"meeting": "...", "parties": {"A": {"name", "language"}, "B": {...}}, "utterances": [{"speaker": "A", "timestamp": "...", "transcript": "..."}]}`
or a bare list of utterances, or text lines `A: hello` / `[2026-10-14T09:00:05+08:00] B: selamat pagi`.

## Business rules (`config/rules.json` can tune the numbers)
* **REJECT** – empty translation, or the language is not English/Indonesian/Chinese.
* **TENSION** – tone is angry/frustrated **and** intensity ≥ 4 **and** tone confidence ≥ 0.8.
* **CHECK** – language or translation confidence < 0.6, or the speaker used another language than set for that party.
* **ACCEPT** – everything else. Attention score = intensity × 10 + tone weight (0-100).

## Tests & CI
`python -m unittest discover -s tests -t .` runs 150+ tests with fake AI/storage/speech (no live API, no microphone). GUI tests that use Streamlit's `AppTest` are skipped
if Streamlit is not installed; `tests/test_gui_voice.py` tests the voice flow against a stand-in for Streamlit, so it always runs.
GitHub Actions ([.github/workflows/tests.yml](.github/workflows/tests.yml)) runs them on every push/PR, both directly
and inside the Docker image.

## Project layout
```
main.py  app.py              entry points (terminal / Streamlit GUI)
meeting_translator/
  models.py  config.py  exceptions.py  pipeline.py  reports.py  background.py  cli.py
  ai_layer/   logic_layer/   data_layer/   io_layer/   gui/
tests/   config/rules.json   input/ (samples)   docs/   Dockerfile   .github/workflows/
```
