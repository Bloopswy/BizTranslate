# COMMIT PLAN – 3 weeks, class-by-class commits

Every step below is split by **class / module** in dependency order so teammates can divide work cleanly and Git history shows clear incremental progress. Run the tests after each completed module with:

```bash
python -m unittest discover -s tests -t .
```

Suggested workflow: one short-lived branch per week (`week1-foundation`, `week2-managers`, `week3-devops`), open a pull request for each, and let the CI workflow check it.

> Before step 1, in your existing repo move the Phase 1 code out of the way so history shows the refactor:
> ```bash
> mkdir phase1_procedural
> git mv ai_manager.py app.py data_manager.py io_manager.py logic_manager.py main.py tests web phase1_procedural/
> git commit -m "chore: archive Phase 1 procedural code before the OOP refactor"
> ```
> (Keep `input/`, `README.md`, `Dockerfile`, `requirements.txt`, `.gitignore` – steps below overwrite them.)

---

## Week 1 – Foundation: domain model, configuration, storage, AI

### 1. Project skeleton
```bash
git add meeting_translator/__init__.py .gitignore .dockerignore .env.example requirements.txt input
git commit -m "chore: add OOP package skeleton, ignore files and sample meeting inputs"
```

### 2. Exceptions & Domain Model (class-by-class)
```bash
# 2a – custom exception hierarchy (TranslatorError, ValidationError, AIError, SpeechError, ...)
git add meeting_translator/exceptions.py
git commit -m "feat(exceptions): add TranslatorError hierarchy for domain, AI, storage and speech errors"

# 2b – domain value objects and entities (Language, Tone, Outcome, Party, MeetingSetup, Utterance, AIAnalysis, Decision, ProcessedRecord)
git add meeting_translator/models.py tests/__init__.py tests/helpers.py tests/test_models.py
git commit -m "feat(models): add Party, MeetingSetup, Utterance, AIAnalysis, Decision and ProcessedRecord with validation and tests"
```
*Concepts:* encapsulation (read-only properties, frozen dataclasses), association, aggregation, composition.

### 3. Configuration
```bash
git add meeting_translator/config.py config/rules.json tests/test_config.py
git commit -m "feat(config): add Settings (env/.env) and validated RuleSettings loaded from config/rules.json"
```

### 4. Data layer (class-by-class)
```bash
# 4a – RecordRepository ABC, JsonRecordRepository, CsvRecordRepository, RepositoryFactory
git add meeting_translator/data_layer/repositories.py tests/fake_storage.py
git commit -m "feat(data): add RecordRepository interface, JSON/CSV repositories and RepositoryFactory"

# 4b – RecordQuery (multi-criteria AND/OR filter)
git add meeting_translator/data_layer/query.py
git commit -m "feat(data): add RecordQuery for multi-criteria AND/OR record filtering"

# 4c – DataManager and package exports
git add meeting_translator/data_layer/data_manager.py meeting_translator/data_layer/__init__.py tests/test_data.py
git commit -m "feat(data): add thread-safe DataManager with corrupt-file recovery and tests"
```
*Concepts:* interface, abstract class, inheritance, polymorphism; missing/corrupt-file handling.

### 5. AI layer (class-by-class)
```bash
# 5a – AIClient ABC and GeminiClient
git add meeting_translator/ai_layer/client.py tests/fake_ai.py
git commit -m "feat(ai): add AIClient interface and GeminiClient HTTP adapter"

# 5b – PromptBuilder (system instruction + context formatting)
git add meeting_translator/ai_layer/prompts.py
git commit -m "feat(ai): add PromptBuilder for structured JSON translation and tone prompts"

# 5c – ResponseParser and ResponseValidator
git add meeting_translator/ai_layer/parsing.py
git commit -m "feat(ai): add ResponseParser and ResponseValidator for strict AI schema checking"

# 5d – AIManager (orchestrates client, prompts, parser, validator with retries)
git add meeting_translator/ai_layer/ai_manager.py meeting_translator/ai_layer/__init__.py tests/test_ai.py
git commit -m "feat(ai): add AIManager with retry/backoff composition and offline tests"
```

---

## Week 2 – Business logic, orchestration, reports, IO

### 6. Logic layer (class-by-class)
```bash
# 6a – Rule ABC and concrete rules (Reject, Tension, Check, Accept) + RuleEngine
git add meeting_translator/logic_layer/rules.py
git commit -m "feat(logic): add abstract Rule, four concrete rule subclasses and RuleEngine"

# 6b – ScoringStrategy
git add meeting_translator/logic_layer/scoring.py
git commit -m "feat(logic): add ScoringStrategy for 0-100 attention scoring"

# 6c – LogicManager and package exports
git add meeting_translator/logic_layer/logic_manager.py meeting_translator/logic_layer/__init__.py tests/test_logic.py
git commit -m "feat(logic): add LogicManager combining RuleEngine and ScoringStrategy with SOLID/LSP tests"
```

### 7. Pipeline
```bash
git add meeting_translator/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): add MeetingPipeline (AI -> logic -> data) and PipelineObserver interface"
```

### 8. NEW FEATURE – meeting reports
```bash
git add meeting_translator/reports.py tests/test_reports.py
git commit -m "feat(reports): add MeetingReport and pluggable ReportSection subclasses with tests"
```

### 9. IO layer (class-by-class)
```bash
# 9a – Console (terminal I/O wrapper)
git add meeting_translator/io_layer/console.py tests/fake_console.py
git commit -m "feat(io): add Console terminal wrapper and FakeConsole test double"

# 9b – MeetingFileParser ABC, JsonMeetingParser, TextMeetingParser, MeetingFileReader
git add meeting_translator/io_layer/meeting_files.py
git commit -m "feat(io): add MeetingFileParser hierarchy and MeetingFileReader"

# 9c – RecordFormatter and Exporter subclasses (TextExporter, JsonExporter, CsvExporter)
git add meeting_translator/io_layer/formatters.py
git commit -m "feat(io): add RecordFormatter and polymorphic Exporter classes"

# 9d – IOManager and ConsoleObserver
git add meeting_translator/io_layer/io_manager.py meeting_translator/io_layer/__init__.py tests/test_io.py
git commit -m "feat(io): add IOManager and ConsoleObserver with tests"
```

### 10. Application and entry point
```bash
git add meeting_translator/cli.py main.py tests/test_cli.py
git commit -m "feat(cli): add Application composition root with interactive and batch modes; add main.py"
```

---

## Week 3 – Advanced deliverables (threading + GUI), DevOps, speech & enhancements

### 11. ADVANCED – threading
```bash
git add meeting_translator/background.py tests/test_background.py
git commit -m "feat(threading): add BackgroundProcessor worker thread and Job progress/cancel handle"
```

### 12. ADVANCED – GUI (Streamlit, class-by-class)
```bash
# 12a – Services and ServiceRegistry (composition root for GUI)
git add meeting_translator/gui/services.py meeting_translator/gui/__init__.py tests/gui_support.py
git commit -m "feat(gui): add Services container for Streamlit GUI"

# 12b – StreamlitGui and app.py entry point
git add meeting_translator/gui/streamlit_app.py app.py tests/test_gui.py
git commit -m "feat(gui): add StreamlitGui (Live, Transcript & report, Filter) backed by BackgroundProcessor"
```

### 13. Docker and CI
```bash
git add Dockerfile .github/workflows/tests.yml
git commit -m "ci: add Dockerfile (serves the GUI) and GitHub Actions workflow running unit and Docker tests"
```

### 14. Documentation
```bash
git add README.md EXPLANATION.md COMMIT_PLAN.md docs
git commit -m "docs: add README, design explanation, UML/data-flow diagrams and commit plan"
```

### 15. EXTRA – speech-to-text (voice input, class-by-class)
```bash
# 15a – SpeechTranscriber interface, Transcription dataclass, WhisperTranscriber
git add meeting_translator/io_layer/speech.py meeting_translator/io_layer/__init__.py meeting_translator/exceptions.py \
        meeting_translator/config.py tests/fake_speech.py tests/test_speech.py tests/test_config.py
git commit -m "feat(speech): add SpeechTranscriber interface and local WhisperTranscriber"

# 15b – wire voice input into IOManager, Application (menu 10) and StreamlitGui
git add meeting_translator/io_layer/io_manager.py meeting_translator/cli.py meeting_translator/gui/services.py \
        meeting_translator/gui/streamlit_app.py tests/test_io.py tests/test_cli.py tests/gui_support.py \
        tests/test_gui.py tests/test_gui_voice.py
git commit -m "feat(voice): add voice input in CLI menu 10 and StreamlitGui (text-only to AI)"

# 15c – dependencies, Docker preload, CI and docs
git add requirements.txt Dockerfile .env.example .github/workflows/tests.yml README.md EXPLANATION.md COMMIT_PLAN.md docs
git commit -m "build: add faster-whisper, optional Whisper preload in Docker and speech documentation"
```

### 16. ENHANCEMENTS – language-based speaker detection, UI charts, tone tuning & continuous VAD
```bash
# 16a – MeetingSetup.party_for_language + WhisperTranscriber meeting-scoped filtering
git add meeting_translator/models.py meeting_translator/io_layer/speech.py tests/fake_speech.py tests/test_speech.py
git commit -m "feat(voice): add MeetingSetup.party_for_language and meeting-scoped Whisper language filtering"

# 16b – CLI & GUI language-based speaker detection
git add meeting_translator/io_layer/io_manager.py meeting_translator/cli.py meeting_translator/gui/streamlit_app.py \
        tests/test_voice_detection.py tests/test_gui_voice.py
git commit -m "feat(voice): auto-detect speaker from spoken language in CLI and StreamlitGui"

# 16c – PromptBuilder tone banter guidance + config/rules.json tuning
git add meeting_translator/ai_layer/prompts.py config/rules.json
git commit -m "fix(ai): reduce false angry/TENSION flags on playful banter and tune rules.json"

# 16d – StreamlitGui card layout and Transcript & report outcome/tone charts
git add meeting_translator/gui/streamlit_app.py tests/test_gui.py
git commit -m "feat(gui): add bordered live cards and outcome/tone/language charts in Transcript & report"

# 16e – continuous hands-free conversation mode (browser Web Audio VAD component)
git add meeting_translator/gui/continuous_mic/index.html meeting_translator/gui/streamlit_app.py \
        tests/test_gui_voice.py README.md COMMIT_PLAN.md
git commit -m "feat(gui): add continuous hands-free conversation recording with browser VAD and speaker detection"
```

---

## Suggested weekly checklist

| Week | Goal | Done when |
|---|---|---|
| 1 | steps 1-5 | models, config, storage, AI all tested; all mandatory OOP concepts started |
| 2 | steps 6-10 | `python main.py --batch` works end-to-end with a real key; new feature visible in menu 7 |
| 3 | steps 11-16 + report | threading + GUI demo-able, CI green (`178/178`), Docker build/run/test verified, 6-page engineering report written, TeamAId CSV exported |

## Things only you can do
* Run once with a **real API key** and demo it (`python main.py --batch` and `streamlit run app.py`), then screenshot for the report.
* Export diagrams from `docs/DESIGN_DIAGRAMS.md` (e.g. mermaid.live) for the 6-page report.
* Keep TeamAId tasks updated weekly and paste the CSV export as a separate file.
* Never commit `.env` or `data/`.
