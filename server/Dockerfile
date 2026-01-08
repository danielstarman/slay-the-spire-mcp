# Slay the Spire MCP Server
# Python 3.11 with uv for fast dependency management

FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Set working directory
WORKDIR /app

# Copy project files
COPY pyproject.toml ./
COPY src/ ./src/

# Install dependencies using uv
RUN uv sync --frozen --no-dev

# Expose ports
# MCP server (Streamable HTTP)
EXPOSE 8000
# Bridge TCP connection
EXPOSE 7777

# Run the server
CMD ["uv", "run", "python", "-m", "slay_the_spire_mcp"]
