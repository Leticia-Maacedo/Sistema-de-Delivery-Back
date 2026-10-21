FROM python:3.12-slim

WORKDIR /app

# Fuso de Brasilia: o codigo grava datas com datetime.now(), e o contêiner
# (Render) roda em UTC por padrao, o que adiantava os horarios em 3 horas.
ENV TZ=America/Sao_Paulo
RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
