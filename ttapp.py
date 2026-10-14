import streamlit as st
import streamlit.components.v1 as components

def detect_browser_language(text_to_analyze: str) -> str:
    """
    Injects a hidden HTML5 script into the browser to detect its language profile.
    Returns the language code (e.g., 'en-US', 'es-ES', 'zh-CN').
    """
    if not text_to_analyze:
        return "No text provided"

    # HTML5/JavaScript payload to fetch browser language settings
    html_code = f"""
    <div id="lang-processor" style="display:none;"></div>
    <script>
        // Get the browser's primary language profile
        const userLanguage = navigator.language || navigator.userLanguage;
        
        // Pass the string back to the parent Streamlit application
        window.parent.postMessage({{
            isStreamlitMessage: true,
            type: "streamlit:setComponentValue",
            value: userLanguage
        }}, "*");
    </script>
    """
    
    # Render the hidden HTML5 component inside your layout frame
    # We assign a height of 0 so it stays completely invisible to the user
    detected_lang = components.html(html_code, height=0)
    
    return detected_lang

# --- Main Application ---
st.title("🌐 HTML5 Language Detection")

# 1. Reuse our auto-clearing input logic
if "stored_input" not in st.session_state:
    st.session_state.stored_input = ""

def on_input_enter():
    st.session_state.stored_input = st.session_state.temp_text
    st.session_state.temp_text = ""

st.text_input(
    "Type something and press Enter:", 
    key="temp_text", 
    on_change=on_input_enter
)

st.divider()

# 2. Process through the HTML5 Function if text is captured
if st.session_state.stored_input:
    st.write(f"**Your Input:** {st.session_state.stored_input}")
    
    # Call the HTML5 interface function
    lang_result = detect_browser_language(st.session_state.stored_input)
    
    # 3. Output the result
    if lang_result:
        st.success(f"🖥️ HTML5 Browser Language Detected: **{lang_result}**")
    else:
        # A quick fallback state while the browser handles the async JS payload
        st.info("Reading browser environment profile...")
