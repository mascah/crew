# A project environment, separate from the controller. Reuse the existing
# Node/Claude base image and add Crew's Python, uv, just and C toolchain.
FROM factory-base
USER root
ARG PNPM_VERSION=10.12.4
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
  && rm -rf /var/lib/apt/lists/* \
  && npm install -g pnpm@${PNPM_VERSION} \
  && mise use -g python@3.13 uv@0.8.24 just@1.51.0 \
  && chmod -R a+rX /opt/mise
USER worker
