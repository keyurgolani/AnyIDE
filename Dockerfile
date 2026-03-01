FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Allow git to operate on host-mounted volumes regardless of directory ownership.
# The container runs as root while workspace files are typically owned by the
# host user — git 2.35.2+ rejects this without explicit safe.directory config.
RUN git config --global --add safe.directory '*'

WORKDIR /app

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY anyide/ ./anyide/

# Admin dashboard (built)
COPY admin/dist/ ./static/admin/

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Create data and secrets directories
RUN mkdir -p /data /secrets

EXPOSE 8080

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["uvicorn", "anyide.main:app", "--host", "0.0.0.0", "--port", "8080"]
