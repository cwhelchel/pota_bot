FROM python:3.10-alpine

WORKDIR /app

COPY requirements.txt .
COPY callsigns.txt .
COPY bot.py .

RUN pip install -r requirements.txt

CMD ["python3", "bot.py"]