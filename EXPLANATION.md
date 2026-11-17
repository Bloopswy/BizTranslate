# EXPLANATION – how the OOP refactor works

This file explains **what was built, why, and where each grading criterion is satisfied**, so you can
defend the design in the lab and write the 6-page engineering report from it.

> Scope: the Phase 2 brief **including two advanced deliverables from section 11: GUI (11.2) and threading
> (11.4)** (section 10 below). The brief only requires *one*, so the extra one is a bonus. Continuous Deployment and
> database integration were not done. The Phase 1 Whisper voice input was first left out (it needs a large model in
> the Docker image) and has since been **added back** as a small, optional `io_layer/speech.py` (section 4c): in the GUI
> you can speak, type or upload; in the terminal you can type, use files, or give an audio file. The AI still only
> ever receives text.

---------------------------------------------------------------------------------------------------

## 1. Big picture

The Phase 1 four-layer pipeline is unchanged; each layer is now a **package with one manager class** at its front:

```
user / file ──► IOManager ──► AIManager ──► LogicManager ──► DataManager
                  (io_layer)   (ai_layer)    (logic_layer)    (data_layer)
                        ▲            MeetingPipeline (pipeline.py) wires the three
                        └─────────── Application (cli.py) builds everything and runs the menu
```

| Phase 1 (procedural) | Phase 2 (OOP) | Responsibility |
|---|---|---|
| `io_manager.py` (944 lines, terminal + Streamlit + Whisper) | `io_layer/` → `IOManager`, `Console`, `MeetingFileReader` + parsers, `RecordFormatter`, `Exporter`s, `SpeechTranscriber`/`WhisperTranscriber` | validate input, turn speech into text, show results |
| `ai_manager.py` | `ai_layer/` → `AIManager`, `AIClient`/`GeminiClient`, `PromptBuilder`, `ResponseParser`, `ResponseValidator` | prompt → API → parse → validate |
| `logic_manager.py` | `logic_layer/` → `LogicManager`, `Rule` + 4 rules, `RuleEngine`, `ScoringStrategy` | evaluate, score, route |
| `data_manager.py` | `data_layer/` → `DataManager`, `RecordRepository` + JSON/CSV, `RecordQuery` | save/load/query |
| dicts everywhere | `models.py` → `Party`, `MeetingSetup`, `Utterance`, `AIAnalysis`, `Decision`, `ProcessedRecord` | typed domain objects |
| `main.py` functions | `pipeline.py` → `MeetingPipeline`; `cli.py` → `Application` | orchestration |
| module-level constants / `.env` loader | `config.py` → `Settings`, `RuleSettings` | configuration |

**It is not just functions wrapped in classes.** Examples of real redesign:

* Records were loose dicts that every function poked at; now they are validated objects
  (`Utterance.create` raises `ValidationError`, `ResponseValidator` returns an `AIAnalysis` or raises
  `AIResponseError`). Nothing unvalidated reaches the logic layer.
* `ai_manager.call_api` returned `None` on failure; now failures are typed exceptions
  (`AIConnectionError`, `AIResponseError`) that `AIManager` catches, logs and retries.
* The `if/elif` file-type and storage-type branching is replaced by polymorphism
  (parsers by extension, repositories by extension, exporters by interface).
* `print()` was spread through the pipeline; now only `Console` prints and the pipeline reports through an
  **observer** interface.
* The business rules were one function with three `if` blocks; now each rule is its own class.

---------------------------------------------------------------------------------------------------

## 2. Mandatory OOP concepts → where to find them

| Concept | Implementation (file → class) | Why it makes sense here |
|---|---|---|
| **Classes & objects** | Every manager, `Party`, `Utterance`, `ProcessedRecord`, `MeetingPipeline`, … instantiated in `Application.build` | the running app is an object graph |
| **Encapsulation** | `Party` (`_name`, read-only properties, no setters); `GeminiClient.__api_key` (name-mangled, hidden from `repr`); `DataManager._records`; `ProcessedRecord._utterance`; frozen dataclasses `AIAnalysis`/`Decision`/`Utterance`/`RuleSettings`. Convention: `_x` = protected/private, `__x` = strongly private, public = API | the API key must never leak; records must not be mutated by accident |
| **Abstract classes** | `Rule` (logic_layer/rules.py), `FileRecordRepository` (data_layer/repositories.py), `MeetingFileParser`, `ReportSection`. `Rule` holds the shared settings + `fires()`; subclasses implement `reasons()` | shared behaviour + a forced hook |
| **Inheritance** | `RejectRule`, `ConfidenceCheckRule`, `LanguageMismatchRule`, `TensionRule` ← `Rule`; `JsonRecordRepository`, `CsvRecordRepository` ← `FileRecordRepository` (which handles missing/corrupt files and atomic saves once); `JsonMeetingParser`/`TextMeetingParser` ← `MeetingFileParser` | subclasses add only what differs |
| **Interfaces** (ABC with only abstract methods) | `AIClient`, `RecordRepository`, `ScoringStrategy`, `Exporter`, `PipelineObserver`, `SpeechTranscriber` | managers depend on contracts, not implementations; tests plug in fakes |
| **Association** | `Utterance → Party` (speaker/listener); `MeetingPipeline → AIManager/LogicManager/DataManager`; `ConsoleObserver → IOManager` | objects collaborate, none owns the others |
| **Aggregation** (part lives independently) | `MeetingSetup ◇ Party`×2 (parties are created outside and passed in); `DataManager ◇ RecordRepository`; `AIManager ◇ AIClient`; `IOManager ◇ Console/MeetingFileReader`; `MeetingReport ◇ ReportSection` | the part is injected and can outlive/replace the whole |
| **Composition** (whole owns the part's lifecycle) | `AIManager` *creates* `PromptBuilder`, `ResponseParser`, `ResponseValidator`; `LogicManager` *creates* its `RuleEngine` (which creates the rules); `ProcessedRecord` owns its `Utterance`+`AIAnalysis`+`Decision` | they are meaningless outside their owner |
| **Polymorphism** | `RuleEngine.evaluate` loops over `Rule`s without asking which kind; `MeetingFileReader` picks a parser from a dict; `DataManager.load/save` work with any `RecordRepository`; `IOManager.export(records, exporter, path)` works with CSV/JSON/text; `MeetingReport.render` loops over `ReportSection`s | no type-specific branching anywhere |

---------------------------------------------------------------------------------------------------

## 3. SOLID (evidence, not definitions)

* **S – Single Responsibility.** `PromptBuilder` only builds text; `ResponseParser` only extracts JSON;
  `ResponseValidator` only checks the schema; `GeminiClient` only does HTTP; `AIManager` only orchestrates
  retries. Phase 1's single `analyse_record` did all of that. Likewise each `Rule` has one reason to change.
* **O – Open/Closed.** To add a business rule, subclass `Rule` and pass it to `RuleEngine`. To add CSV storage
  we added `CsvRecordRepository` and one registry line — `DataManager` was not touched. A new report section
  or export format is likewise one new class. Tests prove it:
  `test_logic.test_open_closed_new_rule_and_scoring_without_editing_manager`,
  `test_reports.test_open_closed_custom_section`, `test_data.FactoryTests`.
* **L – Liskov Substitution.** Every `Rule` returns `list[str]` and has an `outcome`, so `RuleEngine` can
  substitute any rule. `JsonRecordRepository` and `CsvRecordRepository` must obey the *same* contract
  (missing file → `[]`, corrupt file → quarantined, failed save → `False`): `test_data.RepositoryContractTests`
  runs identical checks against both.
* **D – Dependency Inversion** (bonus). `AIManager` depends on `AIClient`, `DataManager` on `RecordRepository`,
  `LogicManager` on `ScoringStrategy`, `IOManager` and the GUI on `SpeechTranscriber`; concrete classes are chosen in one place, `Application.build`
  (the composition root). That is also what lets all tests run **without the live API**.
* **I – Interface Segregation** (bonus). Small single-method interfaces (`AIClient.generate`,
  `Exporter.export`, `ScoringStrategy.score`, `PipelineObserver` with two methods).

---------------------------------------------------------------------------------------------------

## 4. New feature(s) – notes for the report

### 4a. Meeting report generation (`reports.py`)
* **Problem:** after a meeting nobody wants to scroll through every sentence to see how it went.
* **Access:** menu option **7 – Meeting report**; it is shown on screen and saved to `data/reports/<meeting>-report.txt`.
* **Content:** overview (count, time span, average attention score), outcome percentages, tone counts +
  strongest tone, per-speaker stats (incl. tense moments), and the top "moments needing attention".
* **Classes:** `ReportSection` (abstract) ← `OverviewSection`, `OutcomeSection`, `ToneSection`,
  `SpeakerSection`, `AttentionSection`; `MeetingReport`; `IOManager.show_report`.
* **Tests:** `tests/test_reports.py` and `test_cli.test_interactive_session_end_to_end`.

### 4b. Configurable business rules (`config.py` → `RuleSettings`, `config/rules.json`)
* **Problem:** thresholds (tension intensity ≥ 4, confidences, which tones count as tense, how many earlier
  sentences are context) were constants in code.
* **Access:** edit `config/rules.json` (or point `RULES_FILE` elsewhere). Missing/invalid file → logged and defaults used.
* **Classes:** `RuleSettings` (frozen dataclass, validated), consumed by every `Rule` and `LogicManager`.
* **Tests:** `test_logic.RuleSettingsTests`, `test_logic.RoutingTests.test_custom_thresholds_change_routing`.

### 4c. Speech-to-text – voice input (`io_layer/speech.py`)
* **Problem:** people speak in a meeting; typing every sentence is slow. Phase 1 had voice input, Phase 2 first left it out.
* **Access:** GUI → Live tab → *…or record your voice* (record → **Transcribe** → fix the text → **Translate transcript**).
  Terminal → menu **10** (give the path of an audio file; Enter accepts the text, a typed sentence corrects it,
  `/cancel` drops it).
* **Requirement kept:** the AI processes **text only**. The recording is transcribed on this computer by Whisper (library
  `faster-whisper`); only the text reaches `AIManager`. The audio is never stored or sent anywhere, and tests check that
  (`test_cli.test_voice_option_transcribes_an_audio_file_and_translates_it`).
* **Classes:** `SpeechTranscriber` (interface: `transcribe(audio, language) -> Transcription`) ← `WhisperTranscriber`;
  `Transcription` (frozen dataclass: `text`, `language`, `is_empty`); exceptions `SpeechError` ←
  `SpeechUnavailableError`, `TranscriptionError`; `Settings.whisper_model` (`WHISPER_MODEL`, default `base`).
  `IOManager` gains `prompt_audio_path`, `transcribe_audio_file`, `confirm_transcript`; `Services` and
  `Application.build` take an optional `transcriber` (aggregation, injected like `AIClient`).
* **Language:** the speaker's configured language is passed as a *hint* (more accurate than guessing). Without a hint,
  auto-detect is limited to English / Indonesian / Chinese, so Indonesian is not mislabelled as Malay.
* **Design points:** the ~150 MB model loads lazily, once per model name per process, and is shared by every instance
  behind a lock (Streamlit re-creates objects constantly); one transcription runs at a time (CPU-bound shared model);
  `model_loader` can be injected so tests never download a model (Dependency Inversion); the transcript is editable
  before translating because speech recognition mishears names and numbers.
* **Docker:** `PRELOAD_WHISPER=1` (default) downloads the model while building; `--build-arg PRELOAD_WHISPER=0` skips it
  (CI does that, because the tests use a fake model).
* **Tests:** `tests/test_speech.py`, `tests/test_gui_voice.py`, `IOManagerSpeechTests` in `tests/test_io.py`, voice cases
  in `tests/test_cli.py` and `tests/test_config.py`.

(The brief asks for *one* feature; three are provided. Pick whichever you prefer to feature in the report.)

---------------------------------------------------------------------------------------------------

## 5. AI & data requirements checklist

| Requirement | Where |
|---|---|
| Every record passes through the AI | `MeetingPipeline.process` → `AIManager.analyse` (no other way to create a `ProcessedRecord` in the app); `test_pipeline.test_every_record_goes_through_the_ai` |
| AI output influences the logic | `LogicManager.route` uses `tone`, `intensity`, `tone_confidence`, confidences, `detected_language`; `test_logic.test_ai_output_changes_the_outcome` |
| Structured JSON prompt | `PromptBuilder.system_instruction` |
| Parse + validate before use | `ResponseParser` → `ResponseValidator` |
| Multi-condition rule on ≥2 AI fields (preserved from Phase 1) | `TensionRule`: tone **and** intensity **and** tone confidence |
| Persistence across runs | `JsonRecordRepository` (default) / `CsvRecordRepository` (`DATA_FILE=data/records.csv`); `test_pipeline.test_records_persist_across_runs` |
| No hard-coded AI success | the only client in production is `GeminiClient`; fakes live in `tests/` only |

## 6. Exception-handling matrix (for the report)

| Failure | Raised in | Handled in | Result |
|---|---|---|---|
| No API key | `Application.main` | same | friendly message, exit code 1 |
| Network error / timeout / HTTP ≠ 200 / odd JSON envelope | `GeminiClient` → `AIConnectionError` | `AIManager` | log, back-off (2 s, 4 s), retry, finally `None` |
| Reply is not JSON / wrong schema | `ResponseParser`/`ResponseValidator` → `AIResponseError` | `AIManager` | same retry path |
| AI gave up on one sentence | `AIManager` returns `None` | `MeetingPipeline` | `FAILED`, observer shows a message, batch continues |
| Invalid user input (empty, too long, bad speaker) | `Utterance.create` → `ValidationError` | `IOManager` | error shown, re-prompt / skip line |
| Bad meeting file line / bad JSON / unreadable file | parsers / `MeetingFileReader` | same (collected in `ParseResult.errors`) | line skipped, others processed |
| Missing data file | `FileRecordRepository.load_all` | same | start with no records |
| Corrupt data file | same | same | moved to `*.corrupt`, start fresh |
| One unreadable record inside a good file | `ProcessedRecord.from_dict` → `RecordFormatError` | repository | that record skipped and logged |
| Cannot write data/report file | `OSError` | repository / `IOManager.save_text` | `False` + message; record stays in memory |
| Invalid `rules.json` | `RuleSettings.from_dict` → `ValidationError` | `RuleSettings.load` | defaults + log |
| Speech library missing / speech model cannot be loaded | `WhisperTranscriber` → `SpeechUnavailableError` | `IOManager` (terminal), `StreamlitGui` (page) | message (e.g. "pip install faster-whisper"), nothing is translated, app keeps running |
| Recording empty / too large / not decodable | `WhisperTranscriber` → `TranscriptionError` | same | message, nothing is translated |
| Recording contains no speech | `Transcription.is_empty` | same | "no speech was detected", nothing is translated |
| Audio file missing / not an audio type / too large (terminal) | `IOManager._read_audio` | same | message, back to the menu |
| Ctrl-D / end of input | `EOFError` | `Console.ask` | acts like Quit |

## 7. Data-flow (text version; Mermaid diagrams are in `docs/DESIGN_DIAGRAMS.md`)

```
Utterance.create (validated)            AIManager.analyse                      LogicManager.route
   typed text / file line  ──────────►  prompt + last 3 sentences ──► AI ──►   evaluate → score → route
   (IOManager)                          parse → validate → AIAnalysis          Decision(outcome, score, reasons)
                                                                                         │
 IOManager.show_*  ◄── ConsoleObserver ◄── MeetingPipeline ◄── ProcessedRecord ◄─────────┘
                                              └─► DataManager.add/save ─► RecordRepository (JSON/CSV)
```

## 8. Testing

* `python -m unittest discover -s tests -t .` – **150+ tests, no network, no API key, no microphone**.
* Fakes: `tests/fake_ai.py` (`ScriptedClient`, `FailingClient`), `tests/fake_storage.py`, `tests/fake_console.py`, `tests/fake_speech.py` (`FakeTranscriber`, `FakeWhisperModel`).
* Covered: business rules incl. boundaries, scoring, routing precedence, response validation (every schema
  violation), retries/back-off, HTTP failures (via a mocked session), JSON+CSV round-trip, missing/corrupt/unwritable
  storage, queries (AND/OR), file parsers (good and bad input), prompts/menus, reports, the pipeline, persistence
  across runs, whole interactive/batch sessions, and the voice-input flow (terminal and GUI).

## 9. Design decisions you may be asked about

* **Why enums?** `Language`, `Tone`, `Outcome` are `str` enums, so they serialise to the same JSON strings as
  Phase 1 – old `data/records.json` files still load (`ProcessedRecord.from_dict` migrates old field names).
* **Why is the stored format still a flat dict?** Backward compatibility and easy CSV export; the objects are
  rebuilt on load.
* **Why `Application.build` takes an `ai_client`?** So tests (and a future "offline demo") can swap the client
  without touching any other class.
* **Why Whisper on this computer, and not send the audio to Gemma?** The requirement is that the AI processes the
  transcribed text; a local model also keeps recordings private and costs no API quota. The price is a ~150 MB model
  download (done once, or while building the Docker image).
* **Why is voice input menu 10 and not a renumbering?** Options 1-9 (and Quit = 9) keep their numbers, so existing
  tests, docs and muscle memory stay valid. The terminal cannot record from a microphone portably (and Docker has none),
  so it takes an audio file; the GUI records through the browser.
* **Why not a database?** DB integration is an advanced deliverable (section 11.3) that was excluded; the
  `RecordRepository` interface means a `SqliteRecordRepository` would be a drop-in addition later.

---------------------------------------------------------------------------------------------------

## 10. Advanced deliverables

### 10a. Threading (`background.py`, tests in `tests/test_background.py`)
* **Problem:** each AI call takes seconds. On the page/main thread that freezes the interface, and a file of 30
  sentences would lock it for a minute.
* **Design:** `BackgroundProcessor` owns one daemon worker thread and a `queue.Queue` (composition). `submit()`
  returns immediately with a `Job`, a thread-safe progress object (`total`, `done`, `counts`, `progress`,
  `finished`, `wait()`, `cancel()`). The worker runs each sentence through the existing `MeetingPipeline`.
* **Why one worker, not a pool:** every sentence is sent to the AI with the previous 3 sentences of the same meeting
  as context, so order matters. One worker keeps order and still never blocks the caller.
* **Thread safety:** `DataManager` guards its record list with a `threading.RLock` (the GUI reads while the worker
  writes); `Job` uses a lock for its counters and `threading.Event`s for finished/cancel.
* **Robustness:** a bug or AI failure on one sentence is counted as *failed* and the worker carries on
  (`test_unexpected_exception_does_not_kill_the_worker`); `cancel()` stops before the next sentence; `shutdown()`
  stops the worker and a later `submit()` restarts it.
* **Tests:** the job returns while the (fake) AI is still blocked; work runs on thread `translator-worker`; order is
  preserved across jobs; cancel; duplicates; failures; 4 threads x 50 concurrent adds lose nothing.

### 10b. GUI (`gui/`, `app.py`, tests in `tests/test_gui.py`)
* **Design:** `StreamlitGui` is the GUI's user boundary: every `st.*` call lives in that class. `Services` bundles the
  managers, pipeline and background worker so they survive Streamlit's rerun-on-every-click model (cached per API
  key by `ServiceRegistry`). The GUI reuses `AIManager`, `LogicManager`, `DataManager`, `MeetingPipeline`,
  `RecordFormatter`, exporters and `MeetingReport` unchanged, which is the payoff of the 4-manager separation.
* **Threading in the GUI:** submitting a sentence calls `background.submit(...)`, stores the `Job` in
  `st.session_state`, and a `st.fragment(run_every=1)` panel re-draws a progress bar with a Cancel button until the
  job finishes, then triggers a full refresh so the new translation appears.
* **Tabs:** Live (type or upload, latest + previous 3 with timestamps and warnings), Transcript & report
  (summary, report, downloads via `Exporter` polymorphism), Filter (multi-select with AND/OR using `RecordQuery`).
* **Voice input:** under the typed/upload boxes, *record your voice* (`st.audio_input`) → **Transcribe** (the speaker's
  language is the hint) → an editable transcript box → **Translate transcript**, which submits an `Utterance` with
  `input_type="voice"` to the same background worker. On success the box and the recorder reset; on any failure the
  transcript is kept so nothing is lost. See section 4c.
* **Failure handling in the GUI:** empty sentence → error message; no API key → error; bad upload lines → warnings;
  AI failure → "failed" notice, no crash.
* **Tests:** Streamlit's headless `AppTest` drives the real page with a fake AI (no network, no browser):
  first render, type → background job → translation shown, tension warning, validation error, missing key,
  AI failure, report/filter tabs (AND vs OR), new-meeting button. They are skipped automatically if Streamlit is
  not installed.
* **Voice tests:** `AppTest` cannot record audio, so `tests/test_gui.py` puts a transcript into the session as *Transcribe*
  would and checks edit → translate → saved as `voice`. `tests/test_gui_voice.py` runs the real `StreamlitGui` class against
  a fake `streamlit` module (so it runs even where Streamlit is not installed) and covers the record/transcribe step, errors,
  silence, a missing API key and the reset.
