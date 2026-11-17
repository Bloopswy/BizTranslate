FROM python:3.12-slim

ARG WHISPER_MODEL=base
ARG PRELOAD_WHISPER=1
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    WHISPER_MODEL=${WHISPER_MODEL}

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Speech-to-text: download the Whisper model while building so voice input works at once (about 150 MB for "base").
# Skip it with:  docker build --build-arg PRELOAD_WHISPER=0 ...   (faster build; the model then downloads on first use)
# Another size:  docker build --build-arg WHISPER_MODEL=small ...
RUN if [ "$PRELOAD_WHISPER" = "1" ]; then \
        python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type='int8')"; \
    fi

COPY meeting_translator ./meeting_translator
COPY tests ./tests
COPY config ./config
COPY input ./input
COPY main.py app.py ./

# Records, reports and logs are written to /app/data (mount a volume there to keep them).
VOLUME ["/app/data"]
EXPOSE 8501

# Default: the web GUI on http://localhost:8501  (docker run -p 8501:8501 ...)
# Terminal app:  docker run -it ... meeting-translator python main.py
# Tests:         docker run --rm meeting-translator python -m unittest discover -s tests -t .
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
