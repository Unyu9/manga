FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates

ENV BOOKS_ROOT=/books
ENV FLASK_SECRET_KEY=change-me

# Optional: set these to have the tool auto-import sidecars into Grimmory
# via its API instead of clicking Import Sidecar manually each time.
ENV GRIMMORY_BASE_URL=
ENV GRIMMORY_USERNAME=
ENV GRIMMORY_PASSWORD=
ENV GRIMMORY_LIBRARY_NAME=Manga

EXPOSE 5000

CMD ["python3", "app.py"]
