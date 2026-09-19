# syntax=docker/dockerfile:1

FROM ghcr.io/home-assistant/base-python:3.14-alpine3.24-2026.08.0

ARG BUILD_VERSION="dev"
ARG BUILD_ARCH="local"

RUN apk add --no-cache dnsmasq py3-nftables

COPY requirements.txt /tmp/requirements.txt

RUN pip3 install --no-cache-dir --only-binary=:all: -r /tmp/requirements.txt
RUN rm -f /tmp/requirements.txt

COPY virtual_alias /opt/ha-virtual-alias/virtual_alias
COPY run.sh /run.sh

RUN chmod 0755 /run.sh

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/opt/ha-virtual-alias:/usr/lib/python3.14/site-packages

EXPOSE 8101

CMD ["/run.sh"]