import os
import json
import tempfile
import time
from datetime import datetime
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel
from streamlit_mic_recorder import mic_recorder

load_dotenv()
client = genai.Client()

# --- Streamlit UI Configurations ---
st.set_page_config(page_title="AI Meeting Interpreter", page_icon="🗣️", layout="centered")

st.title("Translator APP")
st.write("##############")

# Define the exact data structure we want from Gemini
class TranslationResponse(BaseModel):
    detected_language: str
    translated_text: str

# Persistent Session State initialization
if "dialogue_history" not in st.session_state:
    st.session_state.dialogue_history = []
if "meeting_id" not in st.session_state:
    st.session_state.meeting_id = datetime.now().strftime("%Y%m%d_%H%M%S")

# Functions to handle text submission cleanly without layout refreshes
def handle_text_submission(speaker, text_key, target_lang):
    text_val = st.session_state[text_key].strip()
    if text_val:
        with st.spinner(f"Processing {speaker}'s text entry..."):
            result_obj = process_and_translate_multimodal(text_input=text_val, target_lang=target_lang)
            if result_obj:
                append_to_json_log(speaker, result_obj)
        st.session_state[text_key] = ""

def process_and_translate_multimodal(audio_bytes=None, text_input=None, target_lang=None):
    """Processes input through Gemini and guarantees a structured JSON object response."""
    try:
        contents_payload = []
        
        if audio_bytes:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
                temp_audio.write(audio_bytes)
                temp_audio_path = temp_audio.name
                
            audio_file = client.files.upload(file=temp_audio_path)
            time.sleep(0.5)
            contents_payload.append(audio_file)
        elif text_input:
            contents_payload.append(f"Input Text: {text_input}")
        else:
            return None

        prompt = (
            "You are a professional real-time conversational interpreter specializing exclusively in Chinese, English, and Malay. "
            "Analyze the provided input (audio or text) carefully. "
            "Identify whether the person is using Chinese, English, or Malay, and "
            f"translate the content accurately into {target_lang}."
        )
        contents_payload.append(prompt)

        # Force the model to output a strict JSON layout fitting our Pydantic scheme
        response = client.models.generate_content(
            model="gemini-3.5-flash",
            contents=contents_payload,
            config=types.GenerateContentConfig(
                temperature=0.2,
                response_mime_type="application/json",
                response_schema=TranslationResponse,
            ),
        )
        
        if audio_bytes:
            client.files.delete(name=audio_file.name)
            if os.path.exists(temp_audio_path):
                os.remove(temp_audio_path)
            
        # Parse the reliable JSON response string directly into Python data structures
        data = json.loads(response.text)
        return data
        
    except Exception as e:
        st.error(f"API Error: {str(e)}")
        return None

def append_to_json_log(speaker, result_obj):
    """Logs the structured translation object directly without any line parsing."""
    timestamp = datetime.now().isoformat()
    
    log_entry = {
        "timestamp": timestamp,
        "speaker": speaker,
        "detected_language": result_obj.get("detected_language", "Unknown"),
        "translated_text": result_obj.get("translated_text", "Parsing error")
    }
    
    st.session_state.dialogue_history.append(log_entry)
    
    filename = f"meeting_transcript_{st.session_state.meeting_id}.json"
    existing_data = []
    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            pass
            
    existing_data.append(log_entry)
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(existing_data, f, indent=4, ensure_ascii=False)

# --- Sidebar Controls for File Exporting ---
with st.sidebar:
    st.header("Meeting Exporter")
    st.info(f"Active Session: `{st.session_state.meeting_id}`")
    
    if st.session_state.dialogue_history:
        json_string = json.dumps(st.session_state.dialogue_history, indent=4, ensure_ascii=False)
        st.download_button(
            label="Download JSON Transcript File",
            data=json_string,
            file_name=f"transcript_{st.session_state.meeting_id}.json",
            mime="application/json",
            use_container_width=True
        )
        
        if st.button("Reset Log Records", type="primary", use_container_width=True):
            st.session_state.dialogue_history = []
            st.session_state.meeting_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.rerun()
    else:
        st.write("No recorded speech or text history detected yet.")

# --- Main App Layout Setup ---
AVAILABLE_LANGUAGES = ["English", "Chinese", "Malay"]

st.markdown("###  Target Language Configurations")
lang_col1, lang_col2 = st.columns(2)
with lang_col1:
    lang_a_wants = st.selectbox("Translate Party B -> Party A to:", AVAILABLE_LANGUAGES, index=0, key="lang_a")
with lang_col2:
    lang_b_wants = st.selectbox("Translate Party A -> Party B to:", AVAILABLE_LANGUAGES, index=1, key="lang_b")

st.divider()

col1, col2 = st.columns(2)

with col1:
    st.markdown("### 👤 Party A Interface")
    st.text_input(
        "Type your message & press Enter:", 
        key="input_text_a", 
        on_change=handle_text_submission, 
        args=("Party A", "input_text_a", lang_b_wants)
    )
            
    st.caption("or record your voice:")
    audio_a = mic_recorder(start_prompt="🎙️ Party A: Speak", stop_prompt="⏹️ Stop & Translate", format="wav", key="mic_a")

with col2:
    st.markdown("### 👤 Party B Interface")
    st.text_input(
        "Type your message & press Enter:", 
        key="input_text_b", 
        on_change=handle_text_submission, 
        args=("Party B", "input_text_b", lang_a_wants)
    )
            
    st.caption("or record your voice:")
    audio_b = mic_recorder(start_prompt="🎙️ Party B: Speak", stop_prompt="⏹️ Stop & Translate", format="wav", key="mic_b")

# --- Voice Processing Events ---
if audio_a:
    with st.spinner("Processing Party A's speech log..."):
        result_obj = process_and_translate_multimodal(audio_bytes=audio_a['bytes'], target_lang=lang_b_wants)
        if result_obj:
            append_to_json_log("Party A", result_obj)
        st.rerun()

if audio_b:
    with st.spinner("Processing Party B's speech log..."):
        result_obj = process_and_translate_multimodal(audio_bytes=audio_b['bytes'], target_lang=lang_a_wants)
        if result_obj:
            append_to_json_log("Party B", result_obj)
        st.rerun()

# --- Visual Conversation Log Feed ---
if st.session_state.dialogue_history:
    st.subheader("Text")
    
    for chat in st.session_state.dialogue_history:
        ui_display_text = f"** Language Detected:** {chat['detected_language']}\n\n**🌐 Translation:** {chat['translated_text']}"
        time_parsed = datetime.fromisoformat(chat['timestamp']).strftime("%H:%M:%S")
        
        if chat["speaker"] == "Party A":
            st.chat_message("user").markdown(f"**Party A** [{time_parsed}]\n\n{ui_display_text}")
        else:
            st.chat_message("assistant").markdown(f"**Party B** [{time_parsed}]\n\n{ui_display_text}")
