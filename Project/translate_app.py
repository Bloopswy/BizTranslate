import os
import json
import streamlit as st
from google import genai
from google.genai import types
from gtts import gTTS
import io

# Define persistent storage file path
DATA_FILE = "translation_history.json"

# =========================================================================
# 1. DATA LAYER (data_manager) - Pure Functions Only
# =========================================================================
def load_all_records():
    """Loads all translation records from the local flat JSON database."""
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []

def save_record_to_json(record):
    """Appends and saves a newly processed record to the flat JSON dataset."""
    records = load_all_records()
    records.append(record)
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=4, ensure_ascii=False)
    except IOError:
        pass

def query_records_by_language(target_lang):
    """Filters records based on user search criteria."""
    records = load_all_records()
    return [r for r in records if r.get("target_lang", "").lower() == target_lang.lower()]

# =========================================================================
# 2. AI PROCESSING LAYER (ai_manager) - Decoupled Core Translation Engines
# =========================================================================
def process_text_record_with_ai(text, source_lang, target_lang, api_key):
    """Processes textual inputs and forces structured JSON responses via Gemma 4."""
    if not api_key:
        return {"error": "Missing Gemini API Key."}

    prompt = (
        f"Translate the following text from {source_lang} to {target_lang}.\n"
        f"Text: '{text}'\n\n"
        f"Evaluate the translation complexity (Low, Medium, High) based on vocabulary and length, "
        f"and count the word count of the resulting translation."
    )

    return execute_gemma_generation(prompt, None, api_key)


def process_audio_record_with_ai(audio_bytes, source_lang, target_lang, api_key):
    """Performs Speech-to-Text and translation in one unified Gemma 4 pipeline execution."""
    if not api_key:
        return {"error": "Missing Gemini API Key."}

    prompt = (
        f"Listen carefully to this spoken audio payload. Listen to the language spoken.\n"
        f"1. Transcribe the audio precisely into text.\n"
        f"2. Translate that transcription into {target_lang}.\n"
        f"3. Evaluate the translation complexity (Low, Medium, High) and calculate the final translation word count.\n\n"
        f"Note: If the audio is empty or silent, return an empty transcription string."
    )

    audio_part = types.Part.from_bytes(data=audio_bytes, mime_type="audio/wav")
    return execute_gemma_generation(prompt, audio_part, api_key)


def execute_gemma_generation(prompt, audio_part, api_key):
    """Executes structural generation pipelines targeting the multimodal Gemma 4 node."""
    json_schema = {
        "type": "OBJECT",
        "properties": {
            "transcription": {"type": "STRING", "description": "The precise transcription of input audio (leave blank if input was pure text)."},
            "translated_text": {"type": "STRING", "description": "The converted output text mapped into the target language target context."},
            "complexity": {"type": "STRING", "description": "Linguistic difficulty categorization: Low, Medium, or High."},
            "word_count": {"type": "INTEGER", "description": "The exact total numerical length computation of the output translated text string."}
        },
        "required": ["translated_text", "complexity", "word_count"]
    }

    try:
        client = genai.Client(api_key=api_key)
        
        # Assemble content array payload depending on presence of multimodal parameters
        contents_payload = [audio_part, prompt] if audio_part else [prompt]
        
        response = client.models.generate_content(
            model='gemma-4-26b-a4b-it',  # Employs the 12B modal supporting native structural audio interfaces
            contents=contents_payload,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=json_schema,
                temperature=0.1
            ),
        )
        
        ai_data = json.loads(response.text)
        return {
            "transcription": ai_data.get("transcription", "").strip(),
            "translated_text": ai_data.get("translated_text", "").strip(),
            "complexity": ai_data.get("complexity", "Medium").strip(),
            "word_count": int(ai_data.get("word_count", 0))
        }
    except Exception as e:
        return {"error": f"Gemma 4 Processing / Schema validation failed: {str(e)}"}

# =========================================================================
# 3. LOGIC LAYER (logic_manager) - Pure Business Logic Layer
# =========================================================================
def apply_translation_business_rules(record):
    """Applies domain rules on the AI-enriched record metrics."""
    record["flagged_for_review"] = False
    record["routing_status"] = "Direct Delivery"
    
    # MULTI-CONDITION RULE using structural AI fields
    if record.get("complexity") == "High" and record.get("word_count", 0) > 15:
        record["flagged_for_review"] = True
        record["routing_status"] = "Route to Senior Human Interpreter"
    elif record.get("word_count", 0) == 0:
        record["routing_status"] = "Rejected - Empty Output"
        
    return record

# =========================================================================
# 4. INPUT/OUTPUT LAYER (io_manager via Streamlit UI Controls)
# =========================================================================
def generate_text_to_speech_audio(text, target_lang_str):
    """Converts the translated output text back into synthetic spoken voice waves (TTS)."""
    # Dynamic ISO mapping fallback helper structure matching gTTS specifications
    lang_mapping = {"English": "en", "Malay": "ms", "Chinese": "zh", "Spanish": "es", "French": "fr"}
    lang_code = lang_mapping.get(target_lang_str, "en") # Default fallback structural token to English
    
    try:
        tts = gTTS(text=text, lang=lang_code, slow=False)
        fp = io.BytesIO()
        tts.write_to_fp(fp)
        fp.seek(0)
        return fp
    except Exception:
        return None

def render_party_interface(party_label, widget_key_prefix, api_key):
    """Renders modular interface pipelines for any given operational interaction group block."""
    st.subheader(f"👥 {party_label}")
    src_lang = st.text_input("Your Language", "English", key=f"src_{widget_key_prefix}")
    tgt_lang = st.text_input("Translate to", "Chinese", key=f"tgt_{widget_key_prefix}")
    
    # Structural functional option split choice matrix input toggles
    input_mode = st.radio("Choose Input Mode:", ["Keyboard Text Entry", "Voice Recording / Upload"], key=f"mode_{widget_key_prefix}")
    
    ai_out = None
    input_payload_text = ""
    
    if input_mode == "Keyboard Text Entry":
        input_payload_text = st.text_area("Enter text block to translate:", height=100, key=f"text_{widget_key_prefix}")
        process_triggered = st.button(f"Process {party_label} Text Task", key=f"btn_{widget_key_prefix}")
        
        if process_triggered:
            if not input_payload_text.strip():
                st.error("Input text cannot be empty!")
            else:
                with st.spinner("Processing text strings across models..."):
                    ai_out = process_text_record_with_ai(input_payload_text, src_lang, tgt_lang, api_key)
                    
    else:
        # Streamlit standard audio capture widgets maps safely straight to raw byte wrappers
        audio_file = st.audio_input(f"Record your voice for {party_label}", key=f"audio_{widget_key_prefix}")
        process_triggered = st.button(f"Process {party_label} Audio Task", key=f"btn_aud_{widget_key_prefix}")
        
        if process_triggered:
            if not audio_file:
                st.error("Please record an audio snippet before triggering execution pipelines.")
            else:
                with st.spinner("Gemma 4 converting speech directly into translation..."):
                    raw_audio_bytes = audio_file.read()
                    ai_out = process_audio_record_with_ai(raw_audio_bytes, src_lang, tgt_lang, api_key)
                    # Use extracted native transcription tracking as the foundation identifier log tracking field
                    input_payload_text = ai_out.get("transcription", "[Audio File Input Processing]")

    # Unify presentation layout returns 
    if ai_out:
        if "error" in ai_out:
            st.error(ai_out["error"])
        else:
            record = {
                "original_text": input_payload_text if input_payload_text else ai_out.get("transcription", ""),
                "source_lang": src_lang,
                "target_lang": tgt_lang,
                **ai_out
            }
            enriched = apply_translation_business_rules(record)
            save_record_to_json(enriched)
            
            # Display results text strings outputs to user interface panels
            st.success(f"**Processed Translation Result:** {enriched['translated_text']}")
            if enriched.get("transcription"):
                st.caption(f"🎤 **STT Transcription Log:** {enriched['transcription']}")
            st.info(f"**Complexity:** {enriched['complexity']} | **Routing Verdict:** {enriched['routing_status']}")
            
            # TEXT TO SPEECH (TTS) - Generate and render audio playback block seamlessly inside UI context
            with st.spinner("Synthesizing audio output playback waves..."):
                audio_stream = generate_text_to_speech_audio(enriched['translated_text'], tgt_lang)
                if audio_stream:
                    st.audio(audio_stream, format="audio/mp3")

def run_streamlit_app():
    """Renders the Two-Party system UI interfaces via Streamlit."""
    st.set_page_config(page_title="SIT INF1009 Multimodal Translator", layout="wide")
    st.title("🗣️ Two-Party Multimodal Voice Translator (Procedural)")
    
    # Configuration Panel (Sidebar)
    st.sidebar.header("System Settings")
    api_key = st.sidebar.text_input("Gemini API Key", type="password", value=os.environ.get("GEMINI_API_KEY", ""))
    
    # Navigation Matrix tabs
    tab1, tab2, tab3 = st.tabs(["🚀 Process Multimodal Tasks", "📊 Historical Log Analytics", "🔍 Filter Logs"])
    
    # ------------------ TAB 1: RUN TRANSLATIONS ------------------
    with tab1:
        col1, col2 = st.columns(2)
        with col1:
            render_party_interface("Party A", "party_a", api_key)
        with col2:
            render_party_interface("Party B", "party_b", api_key)

    # ------------------ TAB 2: HISTORY ANALYTICS ------------------
    with tab2:
        st.subheader("📋 Core Engine Analytical Logs")
        records = load_all_records()
        
        if not records:
            st.info("No transactional history saved inside file memory yet.")
        else:
            for idx, r in enumerate(reversed(records), 1):
                with st.expander(f"Task #{idx}: {r['source_lang']} ➔ {r['target_lang']} ({r['routing_status']})"):
                    st.write(f"**Original Text/Transcription:** {r['original_text']}")
                    st.write(f"**Result:** {r['translated_text']}")
                    st.caption(f"Complexity: {r['complexity']} | Words: {r['word_count']} | Human Review Required: {r['flagged_for_review']}")

    # ------------------ TAB 3: SEARCH / FILTER ------------------
    with tab3:
        st.subheader("🔍 Target Language Query Filter")
        query_lang = st.text_input("Enter language to look up (e.g., Chinese):")
        
        if query_lang:
            filtered_data = query_records_by_language(query_lang)
            if not filtered_data:
                st.warning(f"No records found where target language is '{query_lang}'.")
            else:
                st.write(f"Found **{len(filtered_data)}** match(es):")
                st.json(filtered_data)

# =========================================================================
# GLOBAL RUN TRIGGER
# =========================================================================
if __name__ == "__main__":
    run_streamlit_app()
