FROM python:3.12-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    WHISPER_MODEL=base

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download the speech-to-text model at build time so recording works without a first-run download.
RUN python -c "import os; from faster_whisper import WhisperModel; WhisperModel(os.environ['WHISPER_MODEL'], device='cpu', compute_type='int8')"

COPY *.py ./
COPY tests ./tests
COPY web ./web
COPY input ./input

# Records and logs are written to /app/data (mount a volume there to keep them).
VOLUME ["/app/data"]
EXPOSE 8501

# Web app. For the terminal version run:  docker run ... python main.py --batch
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]
