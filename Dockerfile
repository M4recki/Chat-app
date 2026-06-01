FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
 && rm -rf /var/lib/apt/lists/*

# copy and install requirements
COPY requirements.txt requirements-dev.txt ./
RUN python -m pip install --upgrade pip
RUN pip install -r requirements.txt
# install dev requirements (alembic + dev tools) so migrations can run inside the container
RUN if [ -f requirements-dev.txt ]; then pip install -r requirements-dev.txt; fi

# copy app

# copy entrypoint first so it is available and has execute permission
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# copy rest of app
COPY . /app

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "python.main:app", "--bind", "0.0.0.0:8000", "--workers", "1"]
