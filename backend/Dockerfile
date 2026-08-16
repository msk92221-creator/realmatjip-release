# Cloud Run 배포용 — 로컬은 start_server.bat 사용 (스펙 그대로)
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY fixtures ./fixtures

ENV REALMATJIP_DB=realmatjip.db \
    PYTHONUNBUFFERED=1

# Cloud Run은 PORT 환경변수로 포트를 전달한다
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}
