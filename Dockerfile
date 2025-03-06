FROM python:3.9-slim

WORKDIR /app

# Kopiujemy plik zależności i instalujemy je
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Kopiujemy zawartość folderu "app" z hosta do katalogu /app w kontenerze
COPY app/ /app/

# Debug: wyświetlenie zawartości katalogu /app
RUN ls -la /app/

ENV FLASK_APP=app
ENV FLASK_RUN_HOST=0.0.0.0

EXPOSE 5000

CMD ["python", "app.py"]
