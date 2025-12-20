FROM python:3.11-slim AS builder

ENV APP_HOME=/opt/idcops \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai

WORKDIR $APP_HOME

RUN sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    build-essential \
    libffi-dev \
    python3-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    liblcms2-dev \
    libopenjp2-7-dev \
    libtiff-dev \
    libharfbuzz-dev \
    libfribidi-dev \
    libjpeg62-turbo-dev \
    libpq-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

RUN pip install -U pip setuptools wheel --no-cache -i https://mirrors.aliyun.com/pypi/simple --no-cache-dir

ENV UV_INSTALLER_GITHUB_BASE_URL="https://gh-proxy.com/github.com"
RUN pip install uv -i https://mirrors.aliyun.com/pypi/simple/ --no-cache-dir 2>/dev/null \
    || (curl -LsSf https://gh-proxy.com/https://github.com/astral-sh/uv/releases/latest/download/uv-installer.sh | sh \
    && mv /root/.local/bin/uv /usr/local/bin/)

COPY pyproject.toml uv.lock ${APP_HOME}/
RUN uv sync --locked --no-cache

FROM python:3.11-slim

ENV APP_HOME=/opt/idcops \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DEBIAN_FRONTEND=noninteractive \
    TZ=Asia/Shanghai

WORKDIR $APP_HOME

RUN sed -i 's|deb.debian.org|mirrors.ustc.edu.cn|g' /etc/apt/sources.list.d/debian.sources

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    tzdata \
    ca-certificates \
    curl \
    file \
    netcat-openbsd \
    nmap \
    libpq5 \
    libjpeg62-turbo \
    zlib1g \
    libfreetype6 \
    liblcms2-2 \
    libopenjp2-7 \
    libtiff6 \
    libharfbuzz0b \
    libfribidi0 \
    && ln -sf /usr/share/zoneinfo/${TZ} /etc/localtime \
    && echo ${TZ} > /etc/timezone \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

COPY --from=builder ${APP_HOME}/.venv ${APP_HOME}/.venv
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

ENV PATH="${APP_HOME}/.venv/bin:/usr/local/bin:$PATH"

RUN mkdir -p ${APP_HOME}/static \
    && mkdir -p ${APP_HOME}/media \
    && mkdir -p ${APP_HOME}/media/ml/ \
    && mkdir -p ${APP_HOME}/logs \
    && mkdir -p ${APP_HOME}/db-data \
    && mkdir -p ${APP_HOME}/run

COPY . ${APP_HOME}/

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
