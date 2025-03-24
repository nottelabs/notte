# syntax=docker/dockerfile:1

############################
###### STAGE 1: Build ######
############################

# Use the same base image
FROM python:3.11-slim-bullseye AS builder
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install git and other essential build tools if needed
RUN apt-get update && apt-get install -y \
    git \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy the project into the image
ADD . /app

# Sync the project into a new environment, using the frozen lockfile
WORKDIR /app
RUN uv sync --extra api --frozen
ENV PATH="/app/.venv/bin:$PATH"

# Install patchright dependencies
RUN patchright install --with-deps chromium --only-shell


############################
####### STAGE 2: Run #######
############################

FROM python:3.11-slim-bullseye

WORKDIR /app

# Install required system dependencies for Chromium
RUN apt-get update && apt-get install -y \
    chromium \
    chromium-driver \
    libglib2.0-0 \
    libnss3 \
    libnspr4 \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 \
    libxdamage1 \
    libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy only the virtual environment and application files
COPY --from=builder /app/.env /app/.env
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
COPY --from=builder /app/examples /app/examples
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# Environment setup
ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="$VIRTUAL_ENV/lib/python3.11/site-packages"
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8
ENV PYTHONIOENCODING=UTF-8

# Force headless mode for patchright
ENV HEADLESS=true

# Define the command to run your application
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "examples.fastapi_agent:app", "--host", "0.0.0.0", "--port", "8000"]
# REMBMBER TO START WITH
# docker build -f ./Dockerfile -t notte-api .
# docker run --init -p 8000:8000 notte-api
