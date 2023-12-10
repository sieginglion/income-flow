FROM ubuntu:22.04
RUN apt-get update && \
    apt-get install --no-install-recommends -y \
        ca-certificates \
        curl \
        python3 && \
    rm -rf /var/lib/apt/lists/*
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH=/root/.local/bin:${PATH}

WORKDIR /stock-sense
COPY . .
RUN poetry config virtualenvs.create false && \
    poetry install --only main && \
    rm -rf /root/.cache/pypoetry

USER nobody:nogroup
CMD gunicorn -b 0.0.0.0:80 main:server
