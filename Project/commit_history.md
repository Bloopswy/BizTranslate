| Date | Author | Commit | Message |
| :--- | :--- | :--- | :--- |
| 2026-11-18 | Zachary Yong | `b1efffc` | feat(gui): rename to BizTranslate, add session switcher, declutter views and embed scrollable chat feed |
| 2026-11-18 | Zachary Yong | `8d389b2` | feat(gui,reports): polish UI, secure API key, separate executive summary with PDF export and add meeting selector to filter |
| 2026-11-18 | Zachary Yong | `0f7b68e` | fix(ai): add retry with exponential backoff to meeting summarizer against temporary 503 API demand spikes |
| 2026-11-18 | Zachary Yong | `1236cda` | feat(reports): add hybrid AI and rule-based executive summary to meeting report |
| 2026-11-18 | Zachary Yong | `48c96b1` | feat(gui,speech): redesign UI with collaborative bridge, optimize VAD timings and enhance speech transcription |
| 2026-11-18 | Zachary Yong | `93b7ea6` | docs: add design diagrams, engineering report, CI workflow and voice detection tests |
| 2026-11-18 | Zachary Yong | `c1c378a` | Delete Project/EXPLANATION.md |
| 2026-11-18 | Zachary Yong | `01a7dc0` | Delete |
| 2026-11-18 | Zachary Yong | `1f34fe9` | Merge remote changes |
| 2026-11-18 | Zachary Yong | `91989f0` | feat(gui): add continuous hands-free conversation recording with browser VAD component |
| 2026-11-18 | Jeremy | `fb00c29` | build: add faster-whisper, optional Whisper preload in Docker and speech documentation |
| 2026-11-18 | Jeremy | `4f4c9b6` | feat(voice): add voice input in CLI menu 10 and StreamlitGui (text-only to AI) |
| 2026-11-18 | Jeremy | `764d158` | feat(speech): add SpeechTranscriber interface and local WhisperTranscriber |
| 2026-11-18 | Jay-K-2605717 | `61ac201` | Merge pull request #14 from Bloopswy/master |
| 2026-11-18 | 2605717 | `b00b90a` | Added README and EXPLANATION |
| 2026-11-18 | Jay-K-2605717 | `9d0401c` | Rollback to tests.yml |
| 2026-11-18 | Jay-K-2605717 | `6a8843b` | Moved tests.yml |
| 2026-11-18 | Jay-K-2605717 | `43dbf3f` | Add files via upload |
| 2026-11-18 | Jay-K-2605717 | `1d63301` | Added Dockerfile changes |
| 2026-11-18 | 2605717 | `019b345` | Added Dockerfile and GitHub Workflows |
| 2026-11-18 | Jay-K-2605717 | `785e5d1` | Merge pull request #13 from Bloopswy/master |
| 2026-11-18 | 2605717 | `b890a63` | Added cli.py, test_cli.py and main.py |
| 2026-11-18 | Jay-K-2605717 | `c4729dd` | Changed directories |
| 2026-11-18 | 2605717 | `75c5901` | Feature (CI): Added application composition root with interactive and batch modes and added main.py |
| 2026-11-17 | ArkanaWirasena | `9272a2f` | chore: ignore .env and local data |
| 2026-11-17 | ArkanaWirasena | `8584462` | feat(io): add IOManager and ConsoleObserver with tests |
| 2026-11-17 | ArkanaWirasena | `6e1472b` | feat(io): add RecordFormatter and polymorphic Exporter classes |
| 2026-11-17 | ArkanaWirasena | `5cac832` | feat(io): add MeetingFileParser hierarchy and MeetingFileReader |
| 2026-11-17 | ArkanaWirasena | `35aaf99` | feat(io): add Console terminal wrapper and FakeConsole test double |
| 2026-11-17 | ArkanaWirasena | `f9d7537` | Revert "Add OOP meeting translator: console IO layer and tests" |
| 2026-11-17 | ArkanaWirasena | `7e01df6` | Add OOP meeting translator: console IO layer and tests |
| 2026-11-17 | Bloopswy | `f6ebd60` | feat(reports): add MeetingReport and pluggable ReportSection subclasses with tests |
| 2026-11-17 | Bloopswy | `5ec6507` | feat(pipeline): add MeetingPipeline (AI -> logic -> data) and PipelineObserver interface |
| 2026-11-17 | Bloopswy | `385b728` | feat(pipeline): add MeetingPipeline (AI -> logic -> data) and PipelineObserver interface |
| 2026-11-17 | Zachary Yong | `f8128be` | Merge remote changes |
| 2026-11-17 | Zachary Yong | `f8cb1de` | merge |
| 2026-11-17 | Zachary Yong | `66c8ba7` | merge |
| 2026-11-17 | Bloopswy | `3f8a649` | feat(logic): add LogicManager combining RuleEngine and ScoringStrategy with SOLID/LSP test |
| 2026-11-17 | Bloopswy | `5e27bad` | feat(logic): add ScoringStrategy for 0-100 attention scoring |
| 2026-11-17 | Bloopswy | `172b6b6` | feat(logic): add abstract Rule, four concrete rule subclasses and RuleEngine |
| 2026-11-17 | Bloopswy | `c348e9d` | feat(logic): add LogicManager combining RuleEngine and ScoringStrategy with SOLID/LSP tests |
| 2026-11-17 | Bloopswy | `440731e` | feat(logic): add ScoringStrategy for 0-100 attention scoring |
| 2026-11-17 | Bloopswy | `3271872` | feat(logic): add abstract Rule, four concrete rule subclasses and RuleEngine |
| 2026-11-17 | Zachary Yong | `654658c` | feat(gui): add StreamlitGui (Live, Transcript & report, Filter) backed by BackgroundProcessor |
| 2026-11-17 | Zachary Yong | `3ef9382` | feat(gui): add Services container for Streamlit GUI |
| 2026-11-17 | Zachary Yong | `9c831cb` | feat(threading): add BackgroundProcessor worker thread with progress/cancel Job; DataManager is lock-protected |
| 2026-11-17 | Zachary Yong | `e2b1e88` | feat(ai): add AIManager with retry/backoff composition and offline tests |
| 2026-11-17 | Zachary Yong | `59ebaca` | feat(ai): add ResponseParser and ResponseValidator for strict AI schema checking |
| 2026-11-17 | Zachary Yong | `e036057` | feat(ai): add PromptBuilder for structured JSON translation and tone prompts |
| 2026-11-17 | Zachary Yong | `fb8944a` | feat(ai): add AIClient interface and GeminiClient HTTP adapter |
| 2026-11-17 | Zachary Yong | `0d06a23` | feat(data): add thread-safe DataManager with corrupt-file recovery and tests |
| 2026-11-17 | Zachary Yong | `470c3f9` | feat(data): add RecordQuery for multi-criteria AND/OR record filtering |
| 2026-11-17 | Zachary Yong | `aaf47bb` | feat(data): add RecordRepository interface, JSON/CSV repositories and RepositoryFactory |
| 2026-11-17 | Zachary Yong | `d03e037` | feat(config): add Settings (env/.env) and validated RuleSettings loaded from config/rules.json |
| 2026-11-17 | Zachary Yong | `de1bebe` | feat(models): add Party, MeetingSetup, Utterance, AIAnalysis, Decision and ProcessedRecord with validation and tests |
| 2026-11-17 | Zachary Yong | `673671d` | feat(exceptions): add TranslatorError hierarchy for domain, AI, storage and speech errors |
| 2026-11-17 | Zachary Yong | `d1e7e4d` | chore: add OOP package skeleton, ignore files and sample meeting inputs |
| 2026-11-17 | Zachary Yong | `0839a45` | chore: archive previous code before the OOP refactor |
| 2026-10-14 | Zachary Yong | `2d10d71` | error in data manager |
| 2026-10-14 | Zachary Yong | `d0e5caf` | error in IO manager |
| 2026-10-14 | Zachary Yong | `491c055` | Error in logic manager |
| 2026-10-14 | Jay-K-2605717 | `d5a8921` | Refactor logic in translation evaluation process |
| 2026-10-14 | Zachary Yong | `6126fb0` | error at app.y |
| 2026-10-14 | Zachary Yong | `7d6c2a5` | some small error |
| 2026-10-14 | Zachary Yong | `c989158` | Some wrong entries in app.py |
| 2026-10-14 | Zachary Yong | `84ab8ca` | Add Dockerfile |
| 2026-10-14 | Zachary Yong | `78314ad` | Delete Project/tests/Dockerfile |
| 2026-10-14 | Zachary Yong | `9b15def` | Added dockerfile |
| 2026-10-14 | Zachary Yong | `39a71bc` | add show meeting panel, run batch,run interactive and main |
| 2026-10-14 | Zachary Yong | `45c3cdb` | add load raw records from files, show meeting panel, run batch |
| 2026-10-14 | Zachary Yong | `ca15ab3` | Added process records process record |
| 2026-10-14 | Zachary Yong | `efd48f9` | Added setup logging |
| 2026-10-14 | Zachary Yong | `7ae136f` | Added import |
| 2026-10-14 | Zachary Yong | `9197974` | Added the Streamlit codes |
| 2026-10-14 | Zachary Yong | `a2d59ef` | Add files via upload |
| 2026-10-14 | Zachary Yong | `6384b4b` | added some demo files and recorder.html |
| 2026-10-14 | Jay-K-2605717 | `62a5116` | Added filtering in data_manager.py |
| 2026-10-14 | Jay-K-2605717 | `aa04ec0` | Refactor data_manager.py to improve structure |
| 2026-10-14 | Jay-K-2605717 | `e93ca9a` | Added sequencing function |
| 2026-10-14 | Jay-K-2605717 | `a4ad624` | Added meeting_records function |
| 2026-10-14 | Jay-K-2605717 | `56a0666` | Add list_meetings function to data_manager.py |
| 2026-10-14 | Zachary Yong | `93b9bda` | All the test script |
| 2026-10-14 | Jay-K-2605717 | `ed24e02` | Test for logic_manager |
| 2026-10-14 | Zachary Yong | `7204232` | Add all the instructions README.md |
| 2026-10-14 | Zachary Yong | `167c195` | Delete project-group6 directory |
| 2026-10-14 | Jay-K-2605717 | `bae3bb8` | Tone Weight |
| 2026-10-14 | Jay-K-2605717 | `e0a346d` | Tension |
| 2026-10-14 | Jay-K-2605717 | `4eee03e` | Evaluate |
| 2026-10-14 | Jay-K-2605717 | `8ea33fb` | Outcomes |
| 2026-10-14 | Zachary Yong | `495a53f` | add sort record load record migrate record |
| 2026-10-14 | Zachary Yong | `a21b417` | Add var and import |
| 2026-10-14 | Zachary Yong | `7a559f1` | Merge pull request #12 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `61c0470` | Added import and var |
| 2026-10-14 | Zachary Yong | `cec6f2f` | Merge pull request #11 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `65c2a39` | Merge pull request #10 from Bloopswy/feature/io-display |
| 2026-10-14 | Zachary Yong | `7d20702` | Merge pull request #10 from Bloopswy/feature/io-display |
| 2026-10-14 | ArkanaWirasena | `870d330` | test: add tests for format_clock, formatting and exports |
| 2026-10-14 | ArkanaWirasena | `ad0cee2` | io: add records_to_csv, records_to_text and safe_filename for exports |
| 2026-10-14 | ArkanaWirasena | `b7f5adb` | io: add show_message, show_error and the show_* print wrappers |
| 2026-10-14 | ArkanaWirasena | `91e0146` | io: add count_by, format_transcript and format_summary |
| 2026-10-14 | ArkanaWirasena | `c4fa74f` | io: add format_conversation showing the latest and previous sentences |
| 2026-10-14 | ArkanaWirasena | `59cff78` | io: add format_sentence and format_short_sentence |
| 2026-10-14 | ArkanaWirasena | `ad89b19` | io: add format_clock with time-zone conversion |
| 2026-10-14 | ArkanaWirasena | `7af2b41` | test: add tests for make_utterance, ids and meeting file parsing |
| 2026-10-14 | ArkanaWirasena | `0ba2bf5` | io: add read_meeting_file with error handling |
| 2026-10-14 | ArkanaWirasena | `7b83c61` | io: add parse_meeting_content for JSON objects, lists and text lines |
| 2026-10-14 | ArkanaWirasena | `c2fd2b9` | io: add make_utterance that returns the sentence record dict |
| 2026-10-14 | ArkanaWirasena | `93d33c7` | io: add make_utterance_id so repeated sentences stay distinct |
| 2026-10-14 | ArkanaWirasena | `299f9bd` | io: add other_party and now_iso helpers |
| 2026-10-14 | ArkanaWirasena | `2fe9454` | io: add normalise_setup that validates names and languages |
| 2026-10-14 | ArkanaWirasena | `18dc990` | io: add default_setup returning the two-party meeting dict |
| 2026-10-14 | Zachary Yong | `599b764` | added FFmpeg libraries into requirements.txt |
| 2026-10-14 | Enkhbat | `dbd4a90` | added Streamlit UI entry point (app.py) with live, transcripts and filter tabs |
| 2026-10-14 | Enkhbat | `2a9325c` | added logic_manager.py |
| 2026-10-14 | Enkhbat | `a8d06c9` | added logic_manager.py |
| 2026-10-14 | Jeremy | `807954a` | added describe_party, format and prompt menu |
| 2026-10-14 | Jeremy | `c2492e5` | added prompt_setup |
| 2026-10-14 | Jeremy | `d8179cb` | added prompt_file_choice and list_input_files |
| 2026-10-14 | Jeremy | `7e496f3` | added prompt filter |
| 2026-10-14 | Jeremy | `2a70972` | added prompt speaker and language_or_keep |
| 2026-10-14 | Jeremy | `83037d5` | added prompt sentence |
| 2026-10-14 | Jeremy | `69ec8fe` | added prompt choice |
| 2026-10-14 | Jeremy | `5f39737` | added ask wrapper |
| 2026-10-14 | Bernicelwy2005@gmail.com | `5a0630b` | Added AI response parsing and validation |
| 2026-10-14 | Jeremy | `9128e85` | added test for timestamp and load_env |
| 2026-10-14 | Jeremy | `6f0001d` | added load_env file |
| 2026-10-14 | Jeremy | `9c3dc76` | Valid Timestamp |
| 2026-10-14 | Jeremy | `7d19780` | Adding variables |
| 2026-10-14 | Dregxz | `3bcc008` | Merge pull request #9 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `928cb1d` | add requirement.txt and blank app.py, update readme |
| 2026-10-14 | Dregxz | `5cc8388` | Merge pull request #8 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `9c3028b` | add requirement.txt and blank app.py |
| 2026-10-14 | Zachary Yong | `034876f` | add requirement.txt |
| 2026-10-14 | Dregxz | `60600b3` | Merge pull request #7 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `c437661` | add managers file, blank |
| 2026-10-14 | Dregxz | `cfe1943` | Merge pull request #6 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `c60490a` | add ReadMe, with problem statement and target users |
| 2026-10-14 | Dregxz | `1b662b7` | Merge pull request #5 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `42579c2` | add .gitignore and .dockerignore |
| 2026-10-14 | Dregxz | `610bf7e` | Merge pull request #4 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `3070ec0` | Final |
| 2026-10-14 | Dregxz | `9a7e011` | Delete Project Group6 directory |
| 2026-10-14 | Dregxz | `d0f0794` | Delete voice-triage directory |
| 2026-10-14 | Dregxz | `322def6` | Add files via upload |
| 2026-10-14 | Dregxz | `e2b610e` | Merge pull request #3 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `ce4fd65` | Project |
| 2026-10-14 | Dregxz | `bd91c77` | Delete test |
| 2026-10-14 | Dregxz | `b0a37fe` | Delete requirements.txt |
| 2026-10-14 | Dregxz | `1afe35c` | Delete log_project.txt |
| 2026-10-14 | Dregxz | `f6ff768` | Delete ProjectInitialDetails.md |
| 2026-10-14 | Dregxz | `8392437` | Delete log.txt |
| 2026-10-14 | Dregxz | `33c83cc` | Delete inventory.txt |
| 2026-10-14 | Dregxz | `532a206` | Delete inventory.json |
| 2026-10-14 | Dregxz | `b06b183` | Delete Screenshot 2026-10-01 173749.png |
| 2026-10-14 | Dregxz | `21b7ed7` | Delete Screenshot 2026-09-24 145626.png |
| 2026-10-14 | Dregxz | `884f7a7` | Delete Project.zip |
| 2026-10-14 | Dregxz | `2033404` | Delete Lab5.zip |
| 2026-10-14 | Dregxz | `2ea95a1` | Delete Lab2.zip |
| 2026-10-14 | Dregxz | `3c90e6b` | Delete Lab1.Zip.zip |
| 2026-10-14 | Dregxz | `f11babd` | Delete Lab 4 Zachary 2603760.zip |
| 2026-10-14 | Dregxz | `da39758` | Delete Lab 3 2603760 Zachary Yong.zip |
| 2026-10-14 | Dregxz | `b6a69d9` | Delete data directory |
| 2026-10-14 | Dregxz | `5200eea` | Delete Translate App directory |
| 2026-10-14 | Dregxz | `fef21d5` | Delete Lab5 directory |
| 2026-10-14 | Dregxz | `3a91bb3` | Delete Project directory |
| 2026-10-14 | Dregxz | `eafe1d6` | Delete ttapp.py |
| 2026-10-14 | Dregxz | `ec44533` | Merge pull request #2 from Bloopswy/master |
| 2026-10-14 | Zachary Yong | `f0cf017` | Full Translation App |
| 2026-10-13 | Dregxz | `8c91968` | Merge pull request #1 from Bloopswy/master |
| 2026-10-13 | Zachary Yong | `3daed82` | Merge |
| 2026-10-13 | Zachary Yong | `5e9cacb` | Merge branch 'main' of https://github.com/Bloopswy/BizTranslate |
| 2026-10-13 | Zachary Yong | `0a4f504` | Tone App |
| 2026-10-13 | Dregxz | `6ac441f` | Delete Project directory |
| 2026-10-13 | Zachary Yong | `8169f33` | 3rd Push(fix for docker) |
| 2026-10-13 | Dregxz | `8cbc7d6` | Delete Project directory |
| 2026-10-13 | Dregxz | `7390087` | Delete modular_auditor.py |
| 2026-10-13 | Dregxz | `d77c0f4` | Delete persistent_auditor.py |
| 2026-10-13 | Dregxz | `15a575b` | Delete hello.py |
| 2026-10-13 | Dregxz | `089c526` | Delete inventory_manager.py |
| 2026-10-13 | Dregxz | `6ae87d0` | Delete auditor.py |
| 2026-10-13 | Zachary Yong | `ac37c87` | 2nd Push |
| 2026-10-12 | Dregxz | `2d00e2a` | Delete Project directory |
| 2026-10-12 | Zachary Yong | `a087c9e` | 2st Push |
| 2026-10-12 | Zachary Yong | `0194ad5` | 2st Push |
| 2026-10-09 | Zachary Yong | `9f6e5d2` | 1st Push |
| 2026-10-09 | Zachary Yong | `2ca7a59` | 1st push |
| 2026-10-08 | Zachary Yong | `7d473b9` | Donedd |
| 2026-10-08 | Zachary Yong | `fdbee55` | Doned |
| 2026-10-08 | Zachary Yong | `5fe8150` | Done |
| 2026-10-07 | Zachary Yong | `72a4564` | Save Inventory |
| 2026-10-07 | Zachary Yong | `3282e0d` | ? |
| 2026-10-07 | Zachary Yong | `70178cb` | Update Product |
| 2026-10-07 | Zachary Yong | `855f3fe` | Display All |
| 2026-10-07 | Zachary Yong | `8ccedf0` | Add Product |
| 2026-10-01 | Zachary Yong | `8b43392` | lab 4.4 |
| 2026-09-25 | Zachary Yong | `3227de0` | lab 4.3 |
| 2026-09-25 | Zachary Yong | `aa83ee6` | lab 4.2 |
| 2026-09-25 | Zachary Yong | `5f86ba7` | lab 4.1 |
| 2026-09-24 | Zachary Yong | `85a06f9` | lab 3.8 |
| 2026-09-24 | Zachary Yong | `13fe1ce` | lab 3.7 |
| 2026-09-18 | Zachary Yong | `1b28722` | lab 3.6 |
| 2026-09-18 | Zachary Yong | `a44d5d5` | lab 3.5 |
| 2026-09-18 | Zachary Yong | `2df1f8b` | lab 3.4 |
| 2026-09-18 | Zachary Yong | `d6fbc2e` | lab 3.3 |
| 2026-09-18 | Zachary Yong | `b3c3a98` | lab 3.2 |
| 2026-09-18 | Zachary Yong | `a3e6ced` | lab 3.1 |
| 2026-09-17 | Bloopswy | `f6f0ae2` | Initial project setup |
| 2026-09-11 | Zachary Yong | `039b35e` | Lab 2 |
| 2026-09-04 | Zachary Yong | `f56d90e` | Forth Post |
| 2026-09-04 | Zachary Yong | `b931208` | Third Post |
| 2026-09-04 | Zachary Yong | `58618e4` | Second Post |
| 2026-09-04 | Zachary Yong | `c3f6e4b` | First Post |
