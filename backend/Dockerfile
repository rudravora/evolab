# Backend image for Voroa (or any container host). Build from the repo root:
#   docker build -f backend/Dockerfile -t evolab-backend .
# The agent registry reads shared/schemas, so the build context is the whole repo.
FROM python:3.12.7-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend backend
COPY shared shared
COPY experiments experiments
RUN useradd --create-home evolab && chown -R evolab /srv
USER evolab
EXPOSE 8000
CMD ["sh", "backend/start.sh"]
