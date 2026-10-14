import os
import json
import streamlit as st
import streamlit.components.v1 as components
from google import genai
from google.genai import types
from gtts import gTTS
import io

DATA_FILE = "transcribe.json"