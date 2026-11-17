"""The Streamlit user interface.

All Streamlit calls live in this one class (the GUI is just another user boundary). It talks to
the managers only through a Services object, and never calls the AI on the page thread: sentences
are submitted to the BackgroundProcessor and a self-refreshing panel shows the live progress.
"""

from __future__ import annotations

import base64
import os
from datetime import datetime
from typing import Callable, List, Optional

import streamlit as st
import streamlit.components.v1 as components

from ..background import Job
from ..config import Settings
from ..data_layer import RecordQuery
from ..exceptions import SpeechError
from ..io_layer import CsvExporter, Exporter, JsonExporter, RecordFormatter, TextExporter
from ..models import (DETECTED_LANGUAGES, ClockFormatter, Language, MeetingSetup, Outcome, Party,
                      ProcessedRecord, Tone, Utterance)
from ..reports import MeetingReport
from .services import Services

ServicesProvider = Callable[[str], Services]


class ServiceRegistry:
    """Builds Services once per API key and keeps them across Streamlit reruns."""

    @staticmethod
    @st.cache_resource(show_spinner=False)
    def _cached(api_key: str, env_items: tuple) -> Services:
        return Services.create(Settings(dict(env_items)), api_key)

    @classmethod
    def provider(cls, settings: Settings) -> ServicesProvider:
        env_items = settings.items()  # hashable cache key
        return lambda api_key: cls._cached(api_key, env_items)


class StreamlitGui:
    ICONS = {"TENSION": "🔴", "CHECK": "🟡", "ACCEPT": "🟢", "REJECT": "⚪"}
    TIMEZONES = ["Local", "UTC", "Asia/Singapore", "Asia/Jakarta", "Asia/Shanghai", "Asia/Hong_Kong",
                 "Asia/Tokyo", "Europe/London", "America/New_York", "America/Los_Angeles", "Australia/Sydney"]
    REFRESH_SECONDS = 1.0

    def __init__(self, settings: Settings, services_provider: Optional[ServicesProvider] = None):
        self._settings = settings
        self._provider = services_provider or ServiceRegistry.provider(settings)
        self._services: Optional[Services] = None
        self._tz: Optional[str] = None

    # ================= entry point =================
    def run(self) -> None:
        st.set_page_config(page_title="Meeting Translator", page_icon="🗣️", layout="wide")
        st.markdown(
            "<style>"
            ".block-container { padding-top: 2rem; padding-bottom: 2rem; }"
            "[data-testid='stMetricValue'] { font-size: 1.35rem; }"
            "</style>",
            unsafe_allow_html=True,
        )
        st.title("🗣️ Meeting Translator")
        st.caption("Live interpreter for a two-party business meeting (English / Indonesian / Chinese). "
                   "Local speech-to-text; only text is sent to the AI for translation and tone analysis.")
        api_key, setup = self._sidebar()
        self._services = self._provider(api_key)
        live, transcript, filters = st.tabs(["Live", "Transcript & report", "Filter"])
        with live:
            self._live_tab(setup, api_key)
        with transcript:
            self._transcript_tab(setup)
        with filters:
            self._filter_tab()

    # ================= sidebar =================
    @staticmethod
    def _start_new_meeting() -> None:
        st.session_state["meeting_name"] = "meeting-" + datetime.now().strftime("%Y-%m-%d-%H%M%S")

    def _sidebar(self):
        with st.sidebar:
            st.header("Meeting setup")
            api_key = st.text_input("Gemini API key", value=self._settings.api_key, type="password",
                                    help="Defaults to GEMINI_API_KEY / .env").strip()
            st.divider()
            st.session_state.setdefault("meeting_name", MeetingSetup.default_meeting_name())
            st.text_input("Meeting name", key="meeting_name")
            st.button("Start a new meeting", on_click=self._start_new_meeting, use_container_width=True)
            parties = {}
            defaults = {"A": ("Party A", Language.ENGLISH), "B": ("Party B", Language.INDONESIAN)}
            for party_id in MeetingSetup.PARTY_IDS:
                name, language = defaults[party_id]
                st.divider()
                st.subheader("Party " + party_id)
                chosen_name = st.text_input("Name", value=name, key="name_" + party_id)
                chosen_language = st.selectbox("Language", Language.values(), index=list(Language).index(language),
                                               key="lang_" + party_id)
                parties[party_id] = Party(chosen_name, chosen_language)
            st.divider()
            zone = st.selectbox("Time zone for timestamps", self.TIMEZONES)
            self._tz = None if zone == "Local" else zone
        setup = MeetingSetup(st.session_state.get("meeting_name", ""), parties["A"], parties["B"])
        return api_key, setup

    # ================= live tab =================
    def _live_tab(self, setup: MeetingSetup, api_key: str) -> None:
        services = self._services
        p_a, p_b = setup.party("A"), setup.party("B")
        st.caption("Active meeting: **%s** · **A:** %s ↔ **B:** %s" % (
            setup.meeting, p_a.describe(), p_b.describe()))

        speaker_id = st.radio("Who is speaking?", MeetingSetup.PARTY_IDS, horizontal=True,
                              format_func=lambda pid: "%s: %s" % (pid, setup.party(pid).describe()))
        typed, voice = st.columns(2)
        with typed:
            with st.container(border=True):
                st.markdown("**Type a sentence**")
                with st.form("sentence_form", clear_on_submit=True):
                    text = st.text_area("Sentence", height=110, placeholder="Type what was said…")
                    send = st.form_submit_button("Translate", type="primary", use_container_width=True)
                if send:
                    self._submit_text(setup, speaker_id, text, api_key)
        with voice:
            with st.container(border=True):
                self._voice_input(setup, speaker_id, api_key)

        with st.expander("Upload a meeting file (.json / .txt)", expanded=False):
            upload = st.file_uploader("Choose a .json or .txt meeting file", type=["json", "txt"])
            if upload is not None and st.button("Translate the file", use_container_width=True):
                self._submit_file(setup, upload, api_key)

        self._progress_panel()
        self._show_notice()
        latest, previous = services.data.latest_with_context(setup.meeting, services.logic.settings.context_sentences)
        self._conversation(latest, previous, services.logic.settings.context_sentences)

    def _submit_text(self, setup: MeetingSetup, speaker_id: str, text: str, api_key: str,
                     input_type: str = "text") -> bool:
        """Queue one sentence for translation. True if it was queued, False after showing why not."""
        if not self._api_key_ok(api_key):
            return False
        try:
            utterance = Utterance.create(setup, speaker_id, text, input_type=input_type)
        except Exception as error:  # ValidationError: show it, never crash the page
            st.error(str(error))
            return False
        self._start_job([utterance])
        return True

    # ----- voice input: continuous conversation OR record -> transcribe -> fix -> translate -----
    _continuous_component = None

    @classmethod
    def _continuous_mic(cls):
        if cls._continuous_component is None:
            mic_dir = os.path.join(os.path.dirname(__file__), "continuous_mic")
            cls._continuous_component = components.declare_component("continuous_mic", path=mic_dir)
        return cls._continuous_component(key="continuous_mic", default=None)

    def _voice_input(self, setup: MeetingSetup, speaker_id: str, api_key: str) -> None:
        """Speech-to-text runs on this computer; only the TEXT is sent to the AI, never the audio."""
        st.markdown("**Record voice** (local speech-to-text; only text goes to the AI)")
        if self._services.transcriber is None:
            st.caption("Speech-to-text is not available in this setup.")
            return
        if st.checkbox("Continuous conversation (hands-free)", value=False, key="voice_continuous"):
            st.caption("Speak naturally — pauses automatically detect the speaker's language and translate each sentence.")
            payload = self._continuous_mic()
            if isinstance(payload, dict) and payload.get("seq") is not None:
                if payload["seq"] != st.session_state.get("voice_continuous_seq"):
                    st.session_state["voice_continuous_seq"] = payload["seq"]
                    self._handle_continuous_audio(payload.get("audio_b64", ""), setup, speaker_id, api_key)
            status = st.session_state.get("voice_continuous_status")
            if status:
                st.info(status)
            return
        counter = st.session_state.get("voice_counter", 0)  # changing the key gives a fresh, empty recorder
        auto_detect = st.checkbox("Auto-detect speaker from spoken language", value=True, key="voice_auto_detect")
        if auto_detect:
            prompt = "Record what either party says (auto-detects %s / %s)" % (
                setup.party("A").language.value, setup.party("B").language.value)
        else:
            speaker = setup.party(speaker_id)
            prompt = "Record what %s says (%s)" % (speaker.name, speaker.language.value)
        audio = st.audio_input(prompt, key="voice_audio_%d" % counter)
        if audio is not None and st.button("Transcribe", key="voice_transcribe", use_container_width=True):
            self._transcribe_recording(audio, setup, speaker_id, auto_detect=auto_detect)
        transcript = st.session_state.get("voice_transcript")
        if transcript:
            effective_speaker = st.session_state.get("voice_speaker_id", speaker_id)
            note = st.session_state.get("voice_detection_note")
            if note:
                level, message = note
                (st.warning if level == "warning" else st.info)(message)
            with st.form("voice_form"):
                st.caption("Speaker: %s: %s" % (effective_speaker, setup.party(effective_speaker).describe()))
                edited = st.text_area("Transcript (fix any mistakes before translating)", value=transcript, height=90)
                send = st.form_submit_button("Translate transcript", type="primary", use_container_width=True)
            if send and self._submit_text(setup, effective_speaker, edited, api_key, "voice"):
                st.session_state.pop("voice_transcript", None)
                st.session_state.pop("voice_speaker_id", None)
                st.session_state.pop("voice_detection_note", None)
                st.session_state["voice_counter"] = counter + 1
                st.rerun()  # redraw with an empty recorder and no transcript box

    def _transcribe_recording(self, audio, setup: MeetingSetup, speaker_id: str, auto_detect: bool = False) -> None:
        """Turn the recording into text, auto-detecting the speaker from the language when enabled."""
        hint = None if auto_detect else setup.party(speaker_id).language
        allowed = (setup.party("A").language, setup.party("B").language) if auto_detect else None
        try:
            with st.spinner("Transcribing… (the first run downloads the speech model)"):
                result = self._services.transcriber.transcribe(audio.getvalue(), hint, allowed_languages=allowed)
        except SpeechError as error:
            st.error(str(error))
            return
        if result.is_empty:
            st.warning("No speech was detected. Check your microphone and record again.")
            return
        st.session_state["voice_transcript"] = result.text
        if not auto_detect:
            st.session_state["voice_speaker_id"] = speaker_id
            st.session_state.pop("voice_detection_note", None)
            return
        detected = setup.party_for_language(result.language)
        if detected is not None:
            st.session_state["voice_speaker_id"] = detected
            st.session_state["voice_detection_note"] = (
                "info", "Detected %s → Speaker %s (%s)." % (
                    result.language.value, detected, setup.party(detected).name))
        else:
            st.session_state["voice_speaker_id"] = speaker_id
            reason = ("Could not match spoken language to English/Indonesian/Chinese"
                      if result.language is None
                      else "Detected %s, which does not uniquely match one party" % result.language.value)
            st.session_state["voice_detection_note"] = (
                "warning", "%s; using %s (%s)." % (reason, speaker_id, setup.party(speaker_id).name))

    def _handle_continuous_audio(self, audio_b64: str, setup: MeetingSetup, speaker_id: str, api_key: str) -> None:
        """Transcribe one VAD-segmented utterance, detect its speaker by language, and queue translation."""
        if not audio_b64 or not self._api_key_ok(api_key):
            return
        try:
            audio_bytes = base64.b64decode(audio_b64)
        except (ValueError, TypeError):
            return
        allowed = (setup.party("A").language, setup.party("B").language)
        try:
            result = self._services.transcriber.transcribe(audio_bytes, None, allowed_languages=allowed)
        except SpeechError as error:
            st.error(str(error))
            return
        if result.is_empty:
            return
        detected = setup.party_for_language(result.language)
        effective_speaker = detected if detected is not None else speaker_id
        lang_label = result.language.value if result.language else "Unknown language"
        st.session_state["voice_continuous_status"] = "Heard (%s → %s): %s" % (
            lang_label, setup.party(effective_speaker).name, result.text)
        self._submit_text(setup, effective_speaker, result.text, api_key, "voice")

    def _submit_file(self, setup: MeetingSetup, upload, api_key: str) -> None:
        if not self._api_key_ok(api_key):
            return
        result = self._services.reader.parse_bytes(upload.name, upload.getvalue(), setup)
        for message in result.errors:
            st.warning(message)
        if result.utterances:
            self._start_job(result.utterances)

    @staticmethod
    def _api_key_ok(api_key: str) -> bool:
        if not api_key:
            st.error("Add your Gemini API key in the sidebar first.")
            return False
        return True

    def _start_job(self, utterances: List[Utterance]) -> None:
        st.session_state["job"] = self._services.background.submit(utterances)
        st.session_state.pop("notice", None)

    def _progress_panel(self) -> None:
        """Re-draws itself every second while a job runs, without freezing or reloading the page."""
        job: Optional[Job] = st.session_state.get("job")
        if job is None:
            return
        refresh = None if job.finished else self.REFRESH_SECONDS
        st.fragment(self._draw_progress, run_every=refresh)()

    def _draw_progress(self) -> None:
        job: Optional[Job] = st.session_state.get("job")
        if job is None:
            return
        if job.finished:
            counts = job.counts
            st.session_state["notice"] = ("Done: %(processed)d translated, %(skipped)d already done, "
                                          "%(failed)d failed, %(cancelled)d cancelled." % counts, counts["failed"] > 0)
            st.session_state.pop("job")
            st.rerun()  # full refresh so the new sentence appears below
            return
        st.progress(job.progress, text="Translating… %d of %d sentence(s) done" % (job.done, job.total))
        st.button("Cancel", on_click=job.cancel, key="cancel_%d" % job.id)

    @staticmethod
    def _show_notice() -> None:
        notice = st.session_state.get("notice")
        if notice:
            message, has_failures = notice
            (st.warning if has_failures else st.success)(message)
            if has_failures:
                st.caption("Failed sentences are logged (data/app.log); send them again to retry.")

    # ================= presentation =================
    def _conversation(self, latest: Optional[ProcessedRecord], previous: List[ProcessedRecord], count: int) -> None:
        if latest is None:
            st.info("Nothing has been said in this meeting yet.")
            return
        st.subheader("Latest translation")
        with st.container(border=True):
            icon = self.ICONS.get(latest.outcome, "")
            when = ClockFormatter.format(latest.timestamp, self._tz)
            st.caption("%s **%s** · %s (%s → %s) · `%s`" % (
                icon, latest.outcome, latest.speaker_name, latest.speaker_language, latest.target_language, when))
            st.markdown("## %s" % latest.translation)
            st.write("**Said:** %s" % latest.transcript)
            m1, m2, m3 = st.columns(3)
            m1.metric("Tone", latest.tone)
            m2.metric("Intensity", "%d / 5" % latest.intensity)
            m3.metric("Attention score", "%d / 100" % latest.score)
            if latest.outcome in (Outcome.TENSION.value, Outcome.CHECK.value, Outcome.REJECT.value):
                st.warning("; ".join(latest.reasons))
        st.subheader("Previous %d sentences" % len(previous) if previous else "No earlier sentences")
        for record in reversed(previous):
            with st.container(border=True):
                st.markdown("%s `%s` **%s** (%s) · *%s*  \n%s  \n→ **%s**" % (
                    self.ICONS.get(record.outcome, ""), ClockFormatter.format(record.timestamp, self._tz),
                    record.speaker_name, record.speaker_language, record.tone,
                    record.transcript, record.translation))

    # ================= transcript tab =================
    def _transcript_tab(self, setup: MeetingSetup) -> None:
        data = self._services.data
        meetings = data.meetings()
        if not meetings:
            st.info("No meetings stored yet.")
            return
        index = meetings.index(setup.meeting) if setup.meeting in meetings else 0
        meeting = st.selectbox("Meeting", meetings, index=index)
        records = data.meeting_records(meeting)
        formatter = RecordFormatter(self._tz)
        if records:
            from collections import Counter
            import pandas as pd

            outcome_counts = Counter(r.outcome for r in records)
            columns = st.columns(5)
            columns[0].metric("Sentences", len(records))
            for column, outcome in zip(columns[1:], Outcome):
                column.metric("%s %s" % (self.ICONS[outcome.value], outcome.value.title()),
                              outcome_counts.get(outcome.value, 0))

            tone_counts = Counter(r.tone for r in records)
            language_counts = Counter(r.detected_language for r in records)
            left, right = st.columns(2)
            left.caption("Sentences by tone")
            left.bar_chart(pd.Series({t: tone_counts[t] for t in Tone.values() if t in tone_counts}))
            right.caption("Sentences by language spoken")
            right.bar_chart(pd.Series(dict(language_counts)))
        with st.expander("Summary", expanded=False):
            st.text(formatter.summary(records))
        with st.expander("Meeting report", expanded=True):
            st.text(MeetingReport().render(records, "Meeting report: " + meeting))
        self._download_buttons(records, formatter.safe_filename(meeting))
        st.subheader("Transcript")
        for record in records:
            with st.container(border=True):
                st.markdown("%s `%s` **%s** (%s) · *%s*  \n%s  \n→ **%s**" % (
                    self.ICONS.get(record.outcome, ""), ClockFormatter.format(record.timestamp, self._tz),
                    record.speaker_name, record.speaker_language, record.tone,
                    record.transcript, record.translation))

    def _download_buttons(self, records: List[ProcessedRecord], stem: str) -> None:
        exporters: List[Exporter] = [TextExporter(self._tz), JsonExporter(), CsvExporter()]
        mimes = {".txt": "text/plain", ".json": "application/json", ".csv": "text/csv"}
        for column, exporter in zip(st.columns(len(exporters)), exporters):
            with column:
                st.download_button("Download %s" % exporter.extension, exporter.export(records),
                                   file_name=stem + exporter.extension, mime=mimes[exporter.extension],
                                   key="dl" + exporter.extension)

    # ================= filter tab =================
    def _filter_tab(self) -> None:
        data = self._services.data
        if len(data) == 0:
            st.info("Nothing to filter yet. Translate a sentence first.")
            return
        c1, c2, c3, c4 = st.columns(4)
        tones = c1.multiselect("Tone", Tone.values())
        languages = c2.multiselect("Language spoken", DETECTED_LANGUAGES)
        targets = c3.multiselect("Translated into", Language.values())
        speakers = c4.multiselect("Speaker", sorted({r.speaker_name for r in data.all()}))
        mode = st.radio("When several boxes are filled in, match", ["All of them (AND)", "Any of them (OR)"], horizontal=True)
        with st.expander("More filters"):
            meeting = st.selectbox("Meeting", ["(any)"] + data.meetings())
            outcome = st.selectbox("Outcome", ["(any)"] + [o.value for o in Outcome])
        query = RecordQuery(tones=tones, languages=languages, target_languages=targets, speakers=speakers,
                            match="any" if mode.startswith("Any") else "all",
                            outcome=None if outcome == "(any)" else outcome,
                            meeting=None if meeting == "(any)" else meeting)
        rows = data.query(query)
        st.write("%d of %d sentence(s) match." % (len(rows), len(data)))
        st.dataframe([{
            "meeting": r.meeting, "time": ClockFormatter.format(r.timestamp, self._tz), "speaker": r.speaker_name,
            "said": r.transcript, "translation": r.translation, "tone": r.tone, "intensity": r.intensity,
            "score": r.score, "outcome": r.outcome} for r in rows], use_container_width=True)
