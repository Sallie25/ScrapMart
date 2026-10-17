# 1. Use Python 3.13 as our base environment
FROM python:3.13-slim

# 2. Copy the uv executable from its official image
COPY --from=ghcr.io/astral-sh/uv:0.12.0 /uv /uvx /bin/

# 3. Set the working directory inside the container
WORKDIR /app

# 4. Configure Python and uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_NO_DEV=1 \
    UV_LINK_MODE=copy

# 5. Copy dependency configuration first
COPY pyproject.toml uv.lock ./

# 6. Install locked dependencies
RUN uv sync --locked --no-dev --no-install-project

# 7. Copy application code
COPY app ./app

# 8. Create a non-root user
RUN useradd --create-home --uid 10001 scrapmart \
    && chown -R scrapmart:scrapmart /app

# 9. Run the application as that user
USER scrapmart

# 10. Document the application's port
EXPOSE 8000

# 11. Start FastAPI using Uvicorn
CMD ["/app/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
