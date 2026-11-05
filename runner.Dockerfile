FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    default-jdk-headless \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin runner

COPY runner_entry.py /runner/entrypoint.py
RUN chmod 0555 /runner/entrypoint.py

USER 10001:10001
WORKDIR /tmp
ENTRYPOINT ["python3", "/runner/entrypoint.py"]
