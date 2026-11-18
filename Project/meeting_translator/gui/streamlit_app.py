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
from ..io_layer import CsvExporter, Exporter, JsonExporter, RecordFormatter, SummaryPdfExporter, TextExporter
from ..models import (DETECTED_LANGUAGES, ClockFormatter, Language, MeetingSetup, Outcome, Party,
                      ProcessedRecord, Tone, Utterance)
from ..reports import ExecutiveSummarySection, MeetingReport
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
    FLAGS = {}
    TIMEZONES = ["Local", "UTC", "Asia/Singapore", "Asia/Jakarta", "Asia/Shanghai", "Asia/Hong_Kong",
                 "Asia/Tokyo", "Europe/London", "America/New_York", "America/Los_Angeles", "Australia/Sydney"]
    REFRESH_SECONDS = 1.0

    @classmethod
    def flag_for(cls, language) -> str:
        return ""

    def __init__(self, settings: Settings, services_provider: Optional[ServicesProvider] = None):
        self._settings = settings
        self._provider = services_provider or ServiceRegistry.provider(settings)
        self._services: Optional[Services] = None
        self._tz: Optional[str] = None

    # ================= entry point =================
    def run(self) -> None:
        st.set_page_config(page_title="BizTranslate", page_icon="🌐", layout="wide")
        st.markdown(
            """<style>
            .block-container {
                padding-top: 1.8rem;
                padding-bottom: 3rem;
                max-width: 1250px;
            }
            [data-testid='stMetricValue'] {
                font-size: 1.35rem;
                font-weight: 700;
            }

            /* Collaborative Bilingual Bridge */
            .collab-bridge {
                background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.85));
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 14px;
                padding: 14px 20px;
                margin-bottom: 1.2rem;
                display: flex;
                align-items: center;
                justify-content: space-between;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
            }
            .collab-party {
                display: flex;
                align-items: center;
                gap: 12px;
            }
            /* Hide show/hide password toggle button */
            button[aria-label="Show password"],
            button[aria-label="Hide password"],
            [data-testid="stTextInput"] button {
                display: none !important;
            }

            .collab-flag {
                display: none;
            }
            .chat-scroll-container {
                max-height: 460px;
                overflow-y: auto;
                padding-right: 6px;
                margin-top: 6px;
                border-radius: 8px;
            }
            .chat-scroll-container::-webkit-scrollbar {
                width: 6px;
            }
            .chat-scroll-container::-webkit-scrollbar-thumb {
                background: rgba(255, 255, 255, 0.15);
                border-radius: 4px;
            }
            .collab-details {
                display: flex;
                flex-direction: column;
            }
            .collab-label {
                font-size: 0.72rem;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                color: #94a3b8;
                font-weight: 600;
            }
            .collab-name {
                font-size: 1rem;
                font-weight: 700;
                color: #f8fafc;
            }
            .collab-lang {
                font-size: 0.8rem;
                color: #a5b4fc;
            }
            .collab-center {
                display: flex;
                flex-direction: column;
                align-items: center;
                text-align: center;
                padding: 0 16px;
            }
            .collab-badge {
                background: rgba(99, 102, 241, 0.15);
                border: 1px solid rgba(99, 102, 241, 0.35);
                color: #c7d2fe;
                font-size: 0.78rem;
                font-weight: 600;
                padding: 4px 14px;
                border-radius: 9999px;
                display: inline-flex;
                align-items: center;
                gap: 6px;
                letter-spacing: 0.02em;
            }
            .collab-meeting-name {
                font-size: 0.75rem;
                color: #64748b;
                margin-top: 4px;
            }

            /* Chat bubble cards */
            .chat-bubble-card {
                background: linear-gradient(135deg, rgba(255, 255, 255, 0.035), rgba(255, 255, 255, 0.015));
                border: 1px solid rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                padding: 16px 20px;
                margin-bottom: 12px;
                transition: transform 0.15s ease, border-color 0.15s ease;
            }
            .chat-bubble-card:hover {
                border-color: rgba(99, 102, 241, 0.35);
                transform: translateY(-1px);
            }
            .bubble-meta {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 8px;
                font-size: 0.82rem;
                color: #94a3b8;
            }
            .bubble-translation {
                font-size: 1.25rem;
                font-weight: 700;
                color: #ffffff;
                line-height: 1.4;
                margin-bottom: 8px;
            }
            .bubble-original {
                font-size: 0.88rem;
                color: #cbd5e1;
                background: rgba(0, 0, 0, 0.3);
                border-left: 3px solid #6366f1;
                padding: 6px 12px;
                border-radius: 6px;
                margin-bottom: 12px;
            }
            .bubble-chips {
                display: flex;
                gap: 8px;
                flex-wrap: wrap;
                align-items: center;
            }
            .chip {
                font-size: 0.75rem;
                font-weight: 600;
                padding: 3px 10px;
                border-radius: 6px;
            }
            .chip-accept { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
            .chip-tension { background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3); }
            .chip-check { background: rgba(245, 158, 11, 0.15); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.3); }
            .chip-reject { background: rgba(148, 163, 184, 0.15); color: #cbd5e1; border: 1px solid rgba(148, 163, 184, 0.3); }
            .chip-metric { background: rgba(255, 255, 255, 0.05); color: #94a3b8; border: 1px solid rgba(255, 255, 255, 0.08); }

            /* Primary CTA Buttons */
            div[data-testid="stFormSubmitButton"] > button {
                background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%) !important;
                border: none !important;
                color: #ffffff !important;
                font-weight: 600 !important;
                border-radius: 8px !important;
                transition: box-shadow 0.2s ease, transform 0.1s ease !important;
            }
            div[data-testid="stFormSubmitButton"] > button:hover {
                box-shadow: 0 4px 16px rgba(99, 102, 241, 0.45) !important;
                transform: translateY(-1px);
            }
            </style>""",
            unsafe_allow_html=True,
        )
        st.title("🌐 BizTranslate")
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
            self._filter_tab(setup)

    # ================= sidebar =================
    @staticmethod
    def _start_new_meeting() -> None:
        new_name = "meeting-" + datetime.now().strftime("%Y-%m-%d-%H%M%S")
        st.session_state["meeting_name"] = new_name
        st.session_state["selected_meeting_choice"] = new_name

    def _sidebar(self):
        with st.sidebar:
            st.header("Meeting setup")
            api_key = self._settings.api_key
            if not api_key:
                api_key = st.text_input("Gemini API key", type="password",
                                        help="Enter your Gemini API key").strip()
            else:
                st.caption("🔒 Gemini API: Connected (.env)")
            st.divider()
            st.session_state.setdefault("meeting_name", MeetingSetup.default_meeting_name())

            existing_meetings = []
            if self._services and self._services.data:
                existing_meetings = self._services.data.meetings()
            else:
                try:
                    from ..data_layer import DataManager, RepositoryFactory
                    dm = DataManager(RepositoryFactory.for_path(self._settings.data_path))
                    dm.load()
                    existing_meetings = dm.meetings()
                except Exception:
                    existing_meetings = []

            all_meetings = list(existing_meetings)
            current = st.session_state.get("meeting_name", "")
            if current and current not in all_meetings:
                all_meetings.insert(0, current)

            if len(all_meetings) > 1:
                def _on_meeting_change():
                    st.session_state["meeting_name"] = st.session_state["selected_meeting_choice"]

                idx = all_meetings.index(current) if current in all_meetings else 0
                st.selectbox("Select previous meeting", all_meetings, index=idx, key="selected_meeting_choice",
                             on_change=_on_meeting_change, help="Choose an existing meeting to continue the conversation")
                st.text_input("Active meeting name", key="meeting_name")
            else:
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
        st.markdown(
            f"""
            <div class="collab-bridge">
                <div class="collab-party">
                    <div class="collab-details">
                        <span class="collab-label">Party A</span>
                        <span class="collab-name">{p_a.name}</span>
                        <span class="collab-lang">{p_a.language.value}</span>
                    </div>
                </div>
                <div class="collab-center">
                    <div class="collab-badge">🤝 Bilingual Bridge 🤝</div>
                    <div class="collab-meeting-name">Session: {setup.meeting}</div>
                </div>
                <div class="collab-party" style="justify-content: flex-end; text-align: right;">
                    <div class="collab-details">
                        <span class="collab-label">Party B</span>
                        <span class="collab-name">{p_b.name}</span>
                        <span class="collab-lang">{p_b.language.value}</span>
                    </div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

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
        if detected is None:
            speaker_lang = setup.party(effective_speaker).language
            try:
                fallback_result = self._services.transcriber.transcribe(audio_bytes, speaker_lang)
                if not fallback_result.is_empty:
                    result = fallback_result
            except SpeechError:
                pass
        lang_label = result.language.value if result.language else setup.party(effective_speaker).language.value
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
        icon = self.ICONS.get(latest.outcome, "")
        when = ClockFormatter.format(latest.timestamp, self._tz)
        flag = self.flag_for(latest.speaker_language)
        outcome_chip_class = f"chip-{latest.outcome.lower()}"

        raw_latest = f"""
<div class="chat-bubble-card" style="border-left: 4px solid #6366f1; background: linear-gradient(135deg, rgba(99, 102, 241, 0.08), rgba(255, 255, 255, 0.02));">
<div class="bubble-meta">
<div>
<span style="font-weight: 700; color: #f8fafc; font-size: 0.95rem;">{latest.speaker_name}</span>
<span style="color: #94a3b8; font-size: 0.8rem;">({latest.speaker_language} → {latest.target_language})</span>
<span style="margin-left: 8px; font-size: 0.72rem; background: rgba(99,102,241,0.25); color: #c7d2fe; padding: 2px 8px; border-radius: 4px; font-weight: 700;">LATEST</span>
</div>
<div><code>{when}</code></div>
</div>
<div class="bubble-translation">"{latest.translation}"</div>
<div class="bubble-original"><strong>Said:</strong> {latest.transcript}</div>
<div class="bubble-chips">
<span class="chip {outcome_chip_class}">{icon} {latest.outcome}</span>
<span class="chip chip-metric">🎭 Tone: {latest.tone}</span>
<span class="chip chip-metric">⚡ Intensity: {latest.intensity} / 5</span>
<span class="chip chip-metric">🎯 Attention: {latest.score} / 100</span>
</div>
</div>
"""
        card_html = "\n".join(line.strip() for line in raw_latest.splitlines() if line.strip())
        st.markdown(card_html, unsafe_allow_html=True)
        if latest.outcome in (Outcome.TENSION.value, Outcome.CHECK.value, Outcome.REJECT.value):
            st.warning("; ".join(latest.reasons))

        if previous:
            st.markdown(f"<div style='font-size: 0.82rem; font-weight: 600; color: #94a3b8; text-transform: uppercase; letter-spacing: 0.05em; margin: 16px 0 8px 0;'>Previous {len(previous)} Sentences</div>", unsafe_allow_html=True)
            bubble_cards = []
            for record in reversed(previous):
                p_icon = self.ICONS.get(record.outcome, "")
                p_when = ClockFormatter.format(record.timestamp, self._tz)
                p_outcome_class = f"chip-{record.outcome.lower()}"

                raw_card = f"""
<div class="chat-bubble-card">
<div class="bubble-meta">
<div>
<span style="font-weight: 600; color: #f1f5f9;">{record.speaker_name}</span>
<span style="color: #94a3b8; font-size: 0.78rem;">({record.speaker_language})</span>
</div>
<div><code>{p_when}</code></div>
</div>
<div style="font-size: 1.05rem; font-weight: 600; color: #f8fafc; margin-bottom: 6px;">"{record.translation}"</div>
<div style="font-size: 0.85rem; color: #cbd5e1; background: rgba(0,0,0,0.2); padding: 5px 10px; border-radius: 6px; margin-bottom: 8px;"><strong>Said:</strong> {record.transcript}</div>
<div class="bubble-chips">
<span class="chip {p_outcome_class}">{p_icon} {record.outcome}</span>
<span class="chip chip-metric">🎭 {record.tone}</span>
</div>
</div>
"""
                bubble_cards.append("\n".join(line.strip() for line in raw_card.splitlines() if line.strip()))

            feed_body = "".join(bubble_cards)
            st.markdown(f'<div class="chat-scroll-container">{feed_body}</div>', unsafe_allow_html=True)
        else:
            st.caption("No earlier sentences.")

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

            with st.expander("📊 Visual Analytics & Charts", expanded=False):
                tone_counts = Counter(r.tone for r in records)
                language_counts = Counter(r.detected_language for r in records)
                left, right = st.columns(2)
                left.caption("Sentences by tone")
                left.bar_chart(pd.Series({t: tone_counts[t] for t in Tone.values() if t in tone_counts}))
                right.caption("Sentences by language spoken")
                right.bar_chart(pd.Series(dict(language_counts)))
        with st.expander("Summary", expanded=False):
            st.text(formatter.summary(records))
        with st.expander("Executive summary", expanded=True):
            summary_key = f"ai_summary_{meeting}"
            ai_summary = st.session_state.get(summary_key)
            if self._services and self._services.pipeline and records:
                col1, col2 = st.columns([3, 1])
                with col1:
                    if st.button("✨ Generate AI Executive Summary (Gemini)", key=f"btn_ai_{meeting}"):
                        with st.spinner("Analyzing meeting discussion with Gemini AI..."):
                            summary_result = self._services.pipeline.ai.summarize(records)
                            if summary_result and summary_result.strip():
                                st.session_state[summary_key] = summary_result.strip()
                                st.rerun()
                            else:
                                st.warning("AI model was temporarily busy or unreachable. Showing rule-based summary — click to retry.")
                with col2:
                    if ai_summary and st.button("🔄 Reset Summary", key=f"btn_reset_{meeting}"):
                        st.session_state.pop(summary_key, None)
                        st.rerun()

            if ai_summary:
                st.markdown(ai_summary)
                summary_content = ai_summary
            else:
                rule_lines = ExecutiveSummarySection().lines(records)
                summary_content = "\n".join(rule_lines)
                st.text(summary_content)

            if records:
                pdf_bytes = SummaryPdfExporter.export_pdf(meeting, summary_content)
                st.download_button(
                    label="📄 Download Executive Summary (PDF)",
                    data=pdf_bytes,
                    file_name=f"{formatter.safe_filename(meeting)}_summary.pdf",
                    mime="application/pdf",
                    key=f"dl_pdf_{meeting}",
                )

        with st.expander("Meeting report", expanded=False):
            analytics = MeetingReport.analytics_sections()
            st.text(MeetingReport(sections=analytics).render(records, "Meeting report: " + meeting))
        self._download_buttons(records, formatter.safe_filename(meeting))
        st.subheader("Transcript")
        for record in records:
            with st.container(border=True):
                st.markdown("%s `%s` **%s** (%s) · *%s*  \n%s  \n→ **%s**" % (
                    self.ICONS.get(record.outcome, ""), ClockFormatter.format(record.timestamp, self._tz),
                    record.speaker_name, record.speaker_language, record.tone,
                    record.transcript, record.translation))

    def _download_buttons(self, records: List[ProcessedRecord], stem: str) -> None:
        if not records:
            return
        exporters: List[Exporter] = [TextExporter(self._tz), JsonExporter(), CsvExporter()]
        mimes = {".txt": "text/plain", ".json": "application/json", ".csv": "text/csv"}
        labels = {".txt": "📝 Transcript (.txt)", ".json": "⚙️ Structured (.json)", ".csv": "📊 Data (.csv)"}
        with st.container(border=True):
            st.caption("📥 Export Raw Transcript & Data")
            for column, exporter in zip(st.columns(len(exporters)), exporters):
                with column:
                    st.download_button(labels.get(exporter.extension, "Download %s" % exporter.extension),
                                       exporter.export(records),
                                       file_name=stem + exporter.extension, mime=mimes[exporter.extension],
                                       key="dl" + exporter.extension, use_container_width=True)

    # ================= filter tab =================
    def _filter_tab(self, setup: Optional[MeetingSetup] = None) -> None:
        data = self._services.data
        if len(data) == 0:
            st.info("Nothing to filter yet. Translate a sentence first.")
            return

        meetings = ["(any)"] + data.meetings()
        current_meeting = setup.meeting if setup and setup.meeting in data.meetings() else "(any)"
        index = meetings.index(current_meeting) if current_meeting in meetings else 0
        meeting = st.selectbox("Meeting", meetings, index=index, key="filter_meeting")

        c1, c2, c3, c4 = st.columns(4)
        tones = c1.multiselect("Tone", Tone.values())
        languages = c2.multiselect("Language spoken", DETECTED_LANGUAGES)
        targets = c3.multiselect("Translated into", Language.values())
        matching_records = data.meeting_records(meeting) if meeting != "(any)" else data.all()
        speakers = c4.multiselect("Speaker", sorted({r.speaker_name for r in matching_records}))
        mode = st.radio("When several boxes are filled in, match", ["All of them (AND)", "Any of them (OR)"], horizontal=True)
        with st.expander("More filters"):
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
