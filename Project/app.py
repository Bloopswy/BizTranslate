"""Streamlit entry point:  streamlit run app.py"""

from meeting_translator.config import Settings
from meeting_translator.gui.streamlit_app import StreamlitGui

StreamlitGui(Settings.from_environment()).run()
