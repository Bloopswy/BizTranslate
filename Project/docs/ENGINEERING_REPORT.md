# INF1103 Phase 2 Engineering Report
**Project Title:** Meeting Translator – Object-Oriented Refactoring & Extension  
**Module:** INF1103 Software Engineering  
**Submission:** Phase 2 Deliverable (25% Weightage)  

---

## 1. System Architecture & Phase 1 Refactor

### 1.1 Architectural Overview
The Meeting Translator acts as a live, AI-mediated business interpreter between two parties speaking English, Indonesian, or Chinese. In Phase 1, the procedural codebase relied heavily on a monolithic `io_manager.py` (944 lines) and loosely structured dictionaries where functions directly mutated global or untyped structures. 

In Phase 2, the system was refactored into a decoupled, object-oriented 4-manager architecture linked by a centralized `MeetingPipeline`:
1. **IO Layer (`IOManager`):** Collects and validates inputs (CLI, file, voice), formats presentation, and manages exports.
2. **AI Layer (`AIManager`):** Builds prompts with contextual history, communicates with the LLM via `AIClient`, and strictly parses and validates responses into typed value objects.
3. **Logic Layer (`LogicManager`):** Applies domain-specific business rules (`RejectRule`, `TensionRule`, `ConfidenceCheckRule`, `LanguageMismatchRule`) and computes an Attention Score (0–100) via `ScoringStrategy`.
4. **Data Layer (`DataManager`):** Thread-safe persistence supporting JSON and CSV repositories with corrupt-file quarantine and multi-criteria querying (`RecordQuery`).

```
[User Input / Files / Audio]
              │
              ▼
         ┌───────────┐
         │ IOManager │ (Validates input -> Utterance)
         └─────┬─────┘
               │
               ▼
      ┌─────────────────┐
      │ MeetingPipeline │ ──── (Checks for existing records)
      └────────┬────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌───────────┐       ┌──────────────┐
│ AIManager │       │ LogicManager │
└─────┬─────┘       └──────┬───────┘
      │ (AIAnalysis)       │ (Decision: Outcome & Attention Score)
      └──────────┬─────────┘
                 ▼
         ┌───────────────┐
         │  DataManager  │ (Thread-safe JSON / CSV persistence)
         └───────────────┘
```

---

## 2. Mandatory Object-Oriented Programming (OOP) Concepts

All mandatory OOP concepts specified in the project brief are integrated naturally into the domain architecture:

| Concept | Concrete Implementation & Classes Involved | Architectural Purpose & Justification |
|---|---|---|
| **Classes & Objects** | `Party`, `MeetingSetup`, `Utterance`, `AIAnalysis`, `Decision`, `ProcessedRecord`, `MeetingPipeline`, `Application` | Replaced untyped procedural dictionaries with rich, stateful domain entities and lifecycle managers. |
| **Encapsulation** | `GeminiClient.__api_key`, `Party._name`, `RuleSettings`, frozen `@dataclass(frozen=True)` | Strict access control. The API key is name-mangled (`__api_key`) preventing accidental leaks/logs. Dataclasses are immutable. |
| **Abstract Classes** | `Rule` (abstract operations `fires`, `reasons`), `MeetingFileParser`, `ReportSection`, `FileRecordRepository` | Provides template methods and shared baseline behaviour while forcing derived classes to implement domain operations. |
| **Inheritance** | `TensionRule(Rule)`, `JsonRecordRepository(FileRecordRepository)`, `OverviewSection(ReportSection)` | Specialises behaviour (e.g. `TensionRule` evaluates tone, intensity, and confidence thresholds defined in base). |
| **Interfaces** | `AIClient`, `RecordRepository`, `SpeechTranscriber`, `PipelineObserver`, `Exporter` | Contract-first design using Python's `abc.ABC`. Decouples consumers from concrete technical implementations. |
| **Association** | `Utterance --> Party`, `Application --> MeetingPipeline`, `ConsoleObserver --> IOManager` | Collaborative peer relationships where objects interact without lifecycle ownership or whole-part containment. |
| **Aggregation** | `MeetingSetup o-- Party`, `AIManager o-- AIClient`, `DataManager o-- RecordRepository` | Whole-part relationships where components exist independently (e.g. `Party` exists outside a `MeetingSetup`; `AIClient` can be swapped). |
| **Composition** | `ProcessedRecord *-- Utterance, AIAnalysis, Decision`; `AIManager *-- PromptBuilder, ResponseParser, ResponseValidator` | Strong lifecycle ownership. A `ProcessedRecord` exclusively owns its `AIAnalysis` and `Decision`. `AIManager` manages parser lifecycles. |
| **Polymorphism** | `RuleEngine.evaluate()`, `DataManager.save()`, `IOManager.export()` | Client code executes `.fires()`, `.save_all()`, or `.export()` across diverse subtypes without type-checking or `isinstance` branches. |

---

## 3. SOLID Design Principles Justification

The system explicitly embodies Single Responsibility, Open/Closed, and Liskov Substitution principles:

### 3.1 Single Responsibility Principle (SRP)
In Phase 1, `ai_manager.py` handled prompt templating, HTTP transport, JSON decoding, schema validation, and retry logic. In Phase 2:
- `PromptBuilder` has one reason to change: prompt structure and language instruction formatting.
- `GeminiClient` has one reason to change: HTTP transport protocol, network headers, and endpoint URLs.
- `ResponseParser` & `ResponseValidator` handle raw string extraction and JSON schema enforcement respectively.
- `AIManager` purely orchestrates exponential backoff retries across these specialized workers.

### 3.2 Open/Closed Principle (OCP)
The system is open for extension but closed for modification:
- **Business Rules:** New business constraints are added by subclassing `Rule` and registering it with `RuleEngine`. `LogicManager` and `MeetingPipeline` require zero code edits.
- **Reporting:** Adding a new analysis section to the meeting report only requires creating a subclass of `ReportSection` (e.g., `SpeakerSection`). `MeetingReport` automatically renders it.
- **Persistence:** Adding SQLite or Cloud SQL storage simply involves implementing `RecordRepository`.

### 3.3 Liskov Substitution Principle (LSP)
Every subtype satisfies all behavioral contracts established by its base interface:
- Both `JsonRecordRepository` and `CsvRecordRepository` honor the exact same contract: non-existent files return empty lists (`[]`), corrupted files are quarantined without raising unhandled crashes, and failed writes return `False`.
- All `Rule` subclasses (`RejectRule`, `TensionRule`, `ConfidenceCheckRule`, `LanguageMismatchRule`) accept an `Utterance` and `AIAnalysis` and return a tuple of `(fires: bool, reasons: list[str])`. The engine executes them interchangeably without checking their specific types.

---

## 4. Architectural & Data-Flow Diagrams

### 4.1 Comprehensive UML Class Diagram
```
              <<interface>>
               AIClient
              +generate()
                  ▲
                  │ implements
            GeminiClient
            -__api_key: str
            +generate()
                  ▲
                  │ aggregation
            ┌─────┴─────┐      composition      ┌───────────────┐
            │ AIManager │*---------------------►│ PromptBuilder │
            └─────┬─────┘                       └───────────────┘
                  │                             ┌───────────────────┐
                  │                             │ ResponseValidator │
                  │                             └───────────────────┘
                  │ association
                  ▼
         ┌─────────────────┐  aggregation   ┌──────────────────┐
         │ MeetingPipeline │*--------------►│ PipelineObserver │
         └────────┬────────┘                └────────┬─────────┘
                  │ association                      ▲ implements
                  ▼                                  │
         ┌─────────────────┐                  ConsoleObserver
         │  LogicManager   │                         │ association
         └────────┬────────┘                         ▼
                  │ composition                 ┌───────────┐
                  ▼                             │ IOManager │
            ┌────────────┐                      └─────┬─────┘
            │ RuleEngine │                            │ aggregation
            └─────┬──────┘                            ▼
                  │ aggregates                  ┌───────────┐
                  ▼                             │  Console  │
              <<abstract>>                      └───────────┘
                 Rule
              +fires()
              +reasons()
           ▲      ▲      ▲
           │      │      └─────────────────┐
      RejectRule TensionRule     ConfidenceCheckRule
```

### 4.2 Runtime Data Flow
```
1. Input Capture:   IOManager collects text/voice/file -> Utterance.create() (Validated)
2. Pipeline Check:  MeetingPipeline checks DataManager for duplicate utterance ID (Sha1)
3. AI Enrichment:   AIManager sends Utterance + rolling context (last 5 lines) to AIClient
4. AI Validation:   ResponseParser extracts JSON -> ResponseValidator creates AIAnalysis
5. Logic & Routing: LogicManager evaluates RuleEngine -> generates Decision & Score
6. Entity Creation: ProcessedRecord is constructed from Utterance, AIAnalysis, and Decision
7. Persistence:     DataManager appends record to thread-safe RecordRepository (JSON/CSV)
8. Output Broadcast:PipelineObserver updates IOManager / Console / Streamlit UI live
```

---

## 5. Comprehensive Exception-Handling Matrix

The application adopts a defensive, non-crashing exception management architecture across all boundaries:

| Failure Scenario | Throwing Component | Handling Boundary | User / System Impact & Recovery Strategy |
|---|---|---|---|
| **Missing API Key** | `Settings` / `Application.main` | `Application` (CLI) / `StreamlitGui` (Web) | Execution halts gracefully with a friendly setup notice; exit code 1 in CLI; banner in GUI. |
| **AI Network Timeout / HTTP 500** | `GeminiClient` (`requests.RequestException`) | `AIManager.analyse()` | Transformed to `AIConnectionError`. Exponential backoff retries (2s, 4s). Logged to `data/app.log`. |
| **Malformed AI JSON Response** | `ResponseParser` / `ResponseValidator` | `AIManager.analyse()` | Raises `AIResponseError`. Retried up to 3 times. If unresolved, record fails safely; pipeline continues. |
| **Pipeline AI Failure** | `AIManager` (returns `None`) | `MeetingPipeline.process()` | Sentence marked `ProcessStatus.FAILED`. Storage is protected from corruption; user notified. |
| **Invalid User Sentence Input** | `Utterance.create()` | `IOManager` / `StreamlitGui` | Raises `ValidationError` (empty or >2000 chars). User alerted; re-prompted without app crash. |
| **Corrupt JSON / CSV Storage** | `FileRecordRepository.load_all()` | `FileRecordRepository` | Corrupt file is quarantined to `*.corrupt.<timestamp>` and logged. Fresh store initialized safely. |
| **Unreadable Individual Record** | `ProcessedRecord.from_dict()` | `FileRecordRepository` | Raises `RecordFormatError`. Invalid row skipped and logged; remaining valid records load normally. |
| **Storage Disk Write Error** | `FileRecordRepository.save_all()` | `DataManager` / `IOManager` | Caught `OSError` logged; returns `False`. In-memory session preserved; user warned of write failure. |
| **Audio Format / Size Violation** | `WhisperTranscriber.transcribe()` | `IOManager` / `StreamlitGui` | Raises `TranscriptionError` (empty audio or >25MB). User prompted to record a shorter sentence. |
| **Missing Faster-Whisper Model** | `WhisperTranscriber._load()` | `IOManager` / `StreamlitGui` | Raises `SpeechUnavailableError`. Friendly guidance shown ("pip install faster-whisper"); text mode active. |

---

## 6. New Features & Domain Extensions

Beyond refactoring, four meaningful domain capabilities were introduced:

### 6.1 Automated Meeting Report Generation (`reports.py`)
- **Problem:** Reviewing long business meetings requires extracting trends, friction points, and action items rather than reading full transcripts.
- **Solution:** A modular report generator that compiles meeting duration, sentence volume, outcome breakdown percentages, dominant tones, speaker distribution, and high-attention moments.
- **OOP Architecture:** Built using the Open/Closed Principle via abstract `ReportSection` and concrete subclasses (`OverviewSection`, `OutcomeSection`, `ToneSection`, `SpeakerSection`, `AttentionSection`). Adding a new report section requires zero modifications to `MeetingReport`.

### 6.2 Configurable Business Rules (`config/rules.json`)
- **Problem:** Hardcoded thresholds in Phase 1 prevented tuning sensitivity for different organizational cultures.
- **Solution:** Domain rules dynamically bind to an immutable `RuleSettings` object loaded from `config/rules.json`. Thresholds include `tension_tones`, `tension_min_intensity`, `tension_min_tone_confidence`, and `context_sentences`.

### 6.3 Multi-Criteria Query Engine (`RecordQuery`)
- **Problem:** Basic search in Phase 1 only supported single-field matching.
- **Solution:** `RecordQuery` supports multi-dimensional compound filtering across tones, source languages, target languages, speakers, outcomes, and meeting names with configurable boolean logic (`AND` / `OR`).

### 6.4 Language-Scoped Voice Detection & Hands-Free Web Audio VAD
- **Problem:** Forcing speakers to manually click speaker buttons before each sentence interrupted natural meeting dialogue.
- **Solution:** Integrated browser-level Web Audio Voice Activity Detection (`continuous_mic/index.html`) that segments speech upon pauses (~900ms silence). Slices are passed to `WhisperTranscriber`, which restricts candidate languages to the two active meeting parties (`allowed_languages`), automatically attributing each utterance to Party A or Party B.

---

## 7. Advanced Deliverables: Threading & Web GUI

### 7.1 Multi-Threaded Processing Engine (`background.py`)
- **Design:** AI network latency (1–3 seconds per sentence) would freeze synchronous single-threaded interfaces. The `BackgroundProcessor` manages an internal daemon worker thread consuming from a thread-safe `queue.Queue`.
- **Concurrency & Thread-Safety:**
  - `DataManager` guards its shared record list with a re-entrant lock (`threading.RLock`), allowing simultaneous reads from the GUI while the background worker writes.
  - Submitting an utterance immediately returns a thread-safe `Job` token exposing `progress`, `total`, `done`, `counts`, `finished`, `wait()`, and `cancel()`.
  - Sentence order is strictly preserved so the rolling AI context remains chronologically sound.

### 7.2 Interactive Streamlit Web Interface (`StreamlitGui`)
- **Architecture:** Complete separation of concerns: all Streamlit UI calls are isolated inside `StreamlitGui`. It interacts with the backend strictly through an injected `Services` composition root.
- **Features:** 
  - **Live Tab:** Side-by-side bordered cards for text translation and continuous/push-to-talk voice recording, active meeting status, and responsive progress polling via `st.fragment()`.
  - **Transcript & Report Tab:** 5-column metric summary, side-by-side bar charts (Sentences by Tone and Language Spoken), expandable formatted meeting report, and multi-format download buttons (`.txt`, `.json`, `.csv`).
  - **Filter Tab:** Multi-criteria AND/OR filtering backed by `RecordQuery`.

---

## 8. DevOps, Automated Testing & Verification

### 8.1 100% Offline Automated Testing Strategy
- The test suite comprises **178 automated unit tests** achieving complete code coverage across business rules, scoring, response validation, retry backoffs, thread synchronization, corrupt file quarantine, and UI workflows.
- **Zero Live API or Microphone Dependency:** By leveraging polymorphic interfaces (`AIClient`, `RecordRepository`, `SpeechTranscriber`), tests utilize deterministic test doubles (`ScriptedClient`, `FailingClient`, `FakeTranscriber`, `FakeStorage`).
- The entire 178-test suite runs in under **9 seconds** locally and inside Docker.

### 8.2 Containerization & Docker Setup
A multi-stage `Dockerfile` (Python 3.12-slim) provides instant deployment for both the web interface and automated testing:
- **Run GUI:** `docker run --rm -p 8501:8501 -e GEMINI_API_KEY=your-key -v "${PWD}/data:/app/data" meeting-translator`
- **Run Tests in Container:** `docker run --rm meeting-translator python -m unittest discover -s tests -t .`
- **Speech Model Preload:** Supports build arg `--build-arg PRELOAD_WHISPER=1` for offline Docker environments.

### 8.3 Continuous Integration (CI)
GitHub Actions (`.github/workflows/tests.yml`) executes on every push and pull request:
1. Installs dependencies and executes all 178 tests directly on Python 3.12 runner.
2. Builds the Docker container (`PRELOAD_WHISPER=0`) and runs the entire test suite inside the container, guaranteeing production parity.
