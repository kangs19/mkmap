FROM python:3.12-slim

WORKDIR /app

# 시스템 패키지
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && \
    rm -rf /var/lib/apt/lists/*

# Python 패키지 먼저 (캐시 활용)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 소스 전체 복사
COPY backend/ ./backend/
COPY map_viewer/ ./map_viewer/
COPY metadata/ ./metadata/

# 작업 디렉토리를 backend로 설정 (SQLite, 상대경로 기준)
WORKDIR /app/backend

# 시작 스크립트
COPY start.sh /app/start.sh
RUN chmod +x /app/start.sh

ENV PYTHONUNBUFFERED=1
ENV APP_ENV=production

EXPOSE 8100

CMD ["/app/start.sh"]
