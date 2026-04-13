FROM ubuntu:22.04

# Prevent interactive prompts during installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    python3.10 \
    python3-pip \
    nodejs \
    npm \
    sudo \
    && rm -rf /var/lib/apt/lists/*

# Create miliciano user
RUN useradd -m -s /bin/bash miliciano && \
    echo "miliciano ALL=(ALL) NOPASSWD:ALL" >> /etc/sudoers

# Set working directory
WORKDIR /home/miliciano

# Copy Python requirements
COPY requirements.txt requirements-dev.txt ./
RUN pip3 install --no-cache-dir -r requirements.txt && \
    pip3 install --no-cache-dir -r requirements-dev.txt

# Copy miliciano source
COPY miliciano-poc/ ./miliciano-poc/

# Create symlink for miliciano command
RUN chmod +x ./miliciano-poc/bin/miliciano && \
    ln -s /home/miliciano/miliciano-poc/bin/miliciano /usr/local/bin/miliciano

# Install Node.js dependencies for OpenClaw
# Note: OpenClaw installation happens at runtime via miliciano setup

# Create config directories
RUN mkdir -p \
    /home/miliciano/.config/miliciano/logs \
    /home/miliciano/.hermes/profiles/miliciano \
    /home/miliciano/.openclaw

# Set ownership
RUN chown -R miliciano:miliciano /home/miliciano

# Switch to miliciano user
USER miliciano

# Expose Obsidian graph port
EXPOSE 8765

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD miliciano status --json | grep -q '"hermes"' || exit 1

# Default command
ENTRYPOINT ["miliciano"]
CMD ["shell"]
