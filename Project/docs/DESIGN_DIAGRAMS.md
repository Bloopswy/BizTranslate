# Design diagrams (Mermaid)

GitHub renders these automatically. Export them as images for the engineering report.

## UML class diagram

```mermaid
classDiagram
    direction LR
    %% ---------- domain ----------
    class Party { -_name -_language +name +language +describe() }
    class MeetingSetup { -_meeting -_parties +party(id) +listener_of(id) }
    class Utterance { +id +transcript +timestamp +create() }
    class AIAnalysis { +translation +tone +intensity +confidences }
    class Decision { +outcome +score +reasons }
    class ProcessedRecord { -_utterance -_analysis -_decision -_seq +to_dict() +from_dict() }
    MeetingSetup o-- Party : aggregation (2)
    Utterance --> Party : association
    ProcessedRecord *-- Utterance : composition
    ProcessedRecord *-- AIAnalysis : composition
    ProcessedRecord *-- Decision : composition

    %% ---------- AI ----------
    class AIClient { <<interface>> +generate() }
    class GeminiClient { -__api_key +generate() }
    class AIManager { +analyse() }
    class PromptBuilder
    class ResponseParser
    class ResponseValidator
    AIClient <|.. GeminiClient
    AIManager o-- AIClient : aggregation
    AIManager *-- PromptBuilder : composition
    AIManager *-- ResponseParser : composition
    AIManager *-- ResponseValidator : composition

    %% ---------- logic ----------
    class Rule { <<abstract>> +outcome +reasons() +fires() }
    class RejectRule
    class ConfidenceCheckRule
    class LanguageMismatchRule
    class TensionRule
    class RuleEngine { +evaluate() }
    class ScoringStrategy { <<interface>> +score() }
    class ToneIntensityScoring
    class LogicManager { +evaluate() +score() +route() }
    Rule <|-- RejectRule
    Rule <|-- ConfidenceCheckRule
    Rule <|-- LanguageMismatchRule
    Rule <|-- TensionRule
    RuleEngine o-- Rule
    ScoringStrategy <|.. ToneIntensityScoring
    LogicManager *-- RuleEngine : composition
    LogicManager o-- ScoringStrategy : aggregation

    %% ---------- data ----------
    class RecordRepository { <<interface>> +load_all() +save_all() }
    class FileRecordRepository { <<abstract>> #_read_rows() #_write_rows() }
    class JsonRecordRepository
    class CsvRecordRepository
    class DataManager { +load() +save() +add() +query() }
    class RecordQuery { +matches() }
    RecordRepository <|.. FileRecordRepository
    FileRecordRepository <|-- JsonRecordRepository
    FileRecordRepository <|-- CsvRecordRepository
    DataManager o-- RecordRepository : aggregation
    DataManager ..> RecordQuery

    %% ---------- IO ----------
    class IOManager { +prompt_menu() +show_report() +export() }
    class Console
    class MeetingFileParser { <<abstract>> }
    class JsonMeetingParser
    class TextMeetingParser
    class MeetingFileReader
    class Exporter { <<interface>> +export() }
    class CsvExporter
    class JsonExporter
    class TextExporter
    MeetingFileParser <|-- JsonMeetingParser
    MeetingFileParser <|-- TextMeetingParser
    MeetingFileReader o-- MeetingFileParser
    Exporter <|.. CsvExporter
    Exporter <|.. JsonExporter
    Exporter <|.. TextExporter
    IOManager o-- Console
    IOManager o-- MeetingFileReader

    %% ---------- new feature ----------
    class ReportSection { <<abstract>> +title +lines() }
    class MeetingReport { +render() }
    ReportSection <|-- OverviewSection
    ReportSection <|-- OutcomeSection
    ReportSection <|-- ToneSection
    ReportSection <|-- SpeakerSection
    ReportSection <|-- AttentionSection
    MeetingReport o-- ReportSection
    IOManager *-- MeetingReport

    %% ---------- orchestration ----------
    class PipelineObserver { <<interface>> +on_processed() +on_failed() }
    class ConsoleObserver
    class MeetingPipeline { +process() +process_many() }
    class Application { +build() +run_interactive() +run_batch() +main() }
    PipelineObserver <|.. ConsoleObserver
    MeetingPipeline --> AIManager
    MeetingPipeline --> LogicManager
    MeetingPipeline --> DataManager
    MeetingPipeline o-- PipelineObserver
    ConsoleObserver --> IOManager
    Application *-- MeetingPipeline
    Application *-- IOManager
```

## Data flow

```mermaid
flowchart LR
    U[User typing / voice / meeting file] --> IO[IOManager<br/>validate -> Utterance]
    IO --> P{MeetingPipeline}
    P -->|already stored?| S[SKIPPED]
    P --> AI[AIManager<br/>prompt + context -> Gemma -> parse -> validate]
    AI -->|AIAnalysis| L[LogicManager<br/>evaluate -> score -> route]
    AI -->|failed after retries| F[FAILED - logged, continue]
    L -->|Decision| R[ProcessedRecord]
    R --> D[DataManager -> RecordRepository<br/>JSON / CSV]
    R --> O[ConsoleObserver -> IOManager<br/>show result]
    D --> Q[query / report / export]
    Q --> IO
```

## Routing rules

```mermaid
flowchart TD
    A[AIAnalysis + Utterance] --> R{RejectRule fires?}
    R -->|yes| REJECT
    R -->|no| T{TensionRule fires?<br/>tone AND intensity AND tone confidence}
    T -->|yes| TENSION
    T -->|no| C{Confidence or language-mismatch rule fires?}
    C -->|yes| CHECK
    C -->|no| ACCEPT
```

## Advanced deliverables: threading and GUI

```mermaid
classDiagram
    direction LR
    class Job { +total +done +progress +counts +finished +wait() +cancel() }
    class BackgroundProcessor { -queue -worker thread +submit() +shutdown() }
    class MeetingPipeline
    class Services { +data +logic +pipeline +background +reader }
    class ServiceRegistry { +provider() }
    class StreamlitGui { +run() }
    BackgroundProcessor *-- Job : creates
    BackgroundProcessor --> MeetingPipeline : runs jobs through
    Services *-- BackgroundProcessor
    ServiceRegistry ..> Services : caches
    StreamlitGui --> Services
    StreamlitGui ..> Job : shows progress
```

```mermaid
sequenceDiagram
    participant UI as StreamlitGui (page thread)
    participant BP as BackgroundProcessor
    participant W as worker thread
    participant P as MeetingPipeline
    UI->>BP: submit(utterances)
    BP-->>UI: Job (returns immediately)
    BP->>W: queue.put(job)
    loop every sentence, in order
        W->>P: process(utterance)  (AI -> logic -> data)
        W->>UI: Job.counts updated (thread-safe)
    end
    UI->>UI: fragment re-draws progress every 1 s
    W->>UI: job.finished -> full refresh shows result
```

## Speech-to-text (voice input)

```mermaid
classDiagram
    direction LR
    class SpeechTranscriber { <<interface>> +transcribe(audio, language) Transcription }
    class WhisperTranscriber { -model_name -shared models -locks +transcribe() +pick_supported() }
    class Transcription { <<frozen>> +text +language +is_empty }
    class SpeechError { <<exception>> }
    class SpeechUnavailableError { <<exception>> }
    class TranscriptionError { <<exception>> }
    class IOManager { +prompt_audio_path() +transcribe_audio_file() +confirm_transcript() }
    class Services { +transcriber }
    class StreamlitGui { -_voice_input() -_transcribe_recording() }
    SpeechTranscriber <|.. WhisperTranscriber
    SpeechTranscriber ..> Transcription : returns
    SpeechError <|-- SpeechUnavailableError
    SpeechError <|-- TranscriptionError
    WhisperTranscriber ..> SpeechError : raises
    IOManager o-- SpeechTranscriber
    Services o-- SpeechTranscriber
    StreamlitGui --> Services
```

```mermaid
flowchart LR
    M[Microphone in the browser<br/>or an audio file] --> T[SpeechTranscriber<br/>Whisper, on this computer]
    T --> E[Editable transcript<br/>the user fixes mistakes]
    E --> U[Utterance<br/>input_type = voice]
    U --> P[MeetingPipeline]
    P --> AI[AIManager receives TEXT only,<br/>never the audio]
```
