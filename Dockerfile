FROM debian:bookworm-slim

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive

# 1. Install Python, FFmpeg, and build tools for Manim
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    python3-dev \
    ffmpeg \
    libcairo2-dev \
    libpango1.0-dev \
    pkg-config \
    build-essential \
    wget \
    unzip \
    ca-certificates \
    dvisvgm \
    && rm -rf /var/lib/apt/lists/*

# 2. TeX Live and fonts (from your original Dockerfile)
RUN apt-get update && apt-get install -y --no-install-recommends \
    texlive-latex-recommended \
    texlive-fonts-recommended \
    texlive-lang-other \
    texlive-latex-extra \
    ghostscript \
    fonts-noto-cjk \
    texlive-bibtex-extra \
    texlive-science \
    biber \
    texlive-fonts-extra \
    texlive-plain-generic \
    tex-gyre \
    texlive-luatex \
    texlive-lang-portuguese \
    tipa \
    && rm -rf /var/lib/apt/lists/*

# Custom MTPro2 fonts
RUN wget http://mirrors.ctan.org/fonts/mtp2lite.zip -O /tmp/mtp2lite.zip \
    && unzip /tmp/mtp2lite.zip -d /tmp \
    && TEXMF=$(kpsewhich -var-value TEXMFLOCAL) \
    && cp -r /tmp/mtp2lite/texmf/* $TEXMF/ \
    && texhash \
    && updmap-sys --enable Map=mtpro2.map \
    && rm -rf /tmp/mtp2lite.zip /tmp/mtp2lite

# 3. Setup Python virtual environment
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# 4. Install backend dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir hatchling
RUN pip install --no-cache-dir .

# 5. Copy the rest of the application
COPY . .

# Ensure storage directories exist
RUN mkdir -p /app/artifacts /app/tmp_manim_scenes

EXPOSE 8000

# Start FastAPI server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
