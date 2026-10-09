# Use an official, lightweight Python runtime as the parent base image
FROM python:3.11-slim

# Set system environment variables to prevent Python from writing pyc files or buffering stdout
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory inside the container
WORKDIR /app

# Install critical system audio libraries required by speech packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    portaudio19-dev \
    gcc \
    && rm -rf /lib/apt/lists/*

# Install python pip packages directly to speed up compilation layers
RUN pip install --no-cache-dir \
    streamlit \
    google-genai \
    python-dotenv \
    pydantic \
    streamlit-mic-recorder

# Copy the actual source code application file into the working container directory
COPY translate_app.py /app/translate_app.py

# Expose the standard external port that Streamlit uses natively
EXPOSE 8501

# Configure container healthcheck monitoring parameters
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health

# Command to execute the translation script immediately when the container builds and starts up
ENTRYPOINT ["streamlit", "run", "translate_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
