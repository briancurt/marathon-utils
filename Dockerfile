FROM python:3.6.3

COPY scripts /opt/marathon-utils/

ENV PYTHONUNBUFFERED=1
