# Local engine frontend; dependency acquisition is separate from this offline build.
FROM docker.io/library/python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c
COPY requirements/invoice.lock /opt/invoice.lock
COPY requirements/make.json /opt/make.json
COPY tools/dependencies/wheels.py /opt/tools/dependencies/wheels.py
COPY tools/ops/container_guard.py /opt/tools/ops/container_guard.py
ENV IN_CONTAINER=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /opt
RUN --mount=type=bind,from=dependencies,target=/dependencies,ro \
    python3 -B -m tools.dependencies.wheels install --lock /opt/invoice.lock \
    --make-declaration /opt/make.json --output /dependencies
USER 65532:65532
WORKDIR /workspace
