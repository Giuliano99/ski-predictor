FROM python:3.11-slim-bookworm

ARG TARGETARCH
ARG POWERSHELL_VERSION=7.4.20

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        libcurl4 \
        libgssapi-krb5-2 \
        libicu72 \
        liblttng-ust1 \
        libssl3 \
        libunwind8 \
        zlib1g \
    && case "$TARGETARCH" in \
         arm64) archive_arch="arm64"; archive_sha="4D1A7B468EAE627809EAC5FAE79C4E645CD9362FDF9F626298686B4489EB4724" ;; \
         amd64) archive_arch="x64"; archive_sha="ED8008345C7F5337F5E293145F5E243CE132E5EE4DFC24AC551C45A4B3092181" ;; \
         *) echo "Nicht unterstuetzte Architektur: $TARGETARCH" >&2; exit 1 ;; \
       esac \
    && curl -fsSLo /tmp/powershell.tar.gz \
        "https://github.com/PowerShell/PowerShell/releases/download/v${POWERSHELL_VERSION}/powershell-${POWERSHELL_VERSION}-linux-${archive_arch}.tar.gz" \
    && echo "${archive_sha}  /tmp/powershell.tar.gz" | sha256sum -c - \
    && mkdir -p /opt/microsoft/powershell/7 \
    && tar -xzf /tmp/powershell.tar.gz -C /opt/microsoft/powershell/7 \
    && chmod +x /opt/microsoft/powershell/7/pwsh \
    && ln -s /opt/microsoft/powershell/7/pwsh /usr/local/bin/pwsh \
    && rm -f /tmp/powershell.tar.gz \
    && apt-get purge -y --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY services/api/requirements.txt /tmp/api-requirements.txt
COPY services/results-importer/requirements.txt /tmp/importer-requirements.txt
RUN pip install --no-cache-dir -r /tmp/api-requirements.txt -r /tmp/importer-requirements.txt

COPY --chown=1000:1000 . /app

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin ski-predictor
USER 1000:1000

EXPOSE 4175

CMD ["python", "services/api/src/server.py", "--host", "0.0.0.0", "--port", "4175", "--no-browser"]
