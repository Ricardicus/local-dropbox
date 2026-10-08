FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080 DATA_DIR=/var/www/hallevault REQUIRE_STORAGE=true
WORKDIR /app
RUN groupadd --gid 10001 vault && useradd --uid 10001 --gid vault --no-create-home vault
COPY server.py ./
COPY public ./public
USER vault
EXPOSE 8080
CMD ["python", "server.py"]
