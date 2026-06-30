FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY templates ./templates

ENV BOOKS_ROOT=/books
ENV FLASK_SECRET_KEY=change-me

EXPOSE 5000

CMD ["python3", "app.py"]
