# syntax=docker/dockerfile:1
FROM docker.io/library/rust:1-bookworm AS builder

WORKDIR /src

# Install minimal build tools for rquickjs-sys and pinned PDFium verification.
RUN apt-get update && apt-get install -y --no-install-recommends \
      cmake \
      curl \
      ca-certificates \
      pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY Cargo.toml Cargo.lock ./
COPY .cargo ./.cargo
COPY src ./src

# Keep single-job build to honor memory limits and match repo Cargo config.
RUN cargo build --release --locked -j 1

# Download and verify the pinned Linux x64 PDFium binary & licenses.
RUN mkdir -p /pdfium \
 && curl --fail --location --retry 2 \
      'https://github.com/bblanchon/pdfium-binaries/releases/download/chromium%2F8111/pdfium-v8-linux-x64.tgz' \
      -o /tmp/pdfium.tgz \
 && echo '01986cb383a89e3a908173c9af4aa97abd470a8f72d6cda6b7f1e391a7e36df1  /tmp/pdfium.tgz' | sha256sum --check \
 && tar -xzf /tmp/pdfium.tgz -C /pdfium \
 && rm -f /tmp/pdfium.tgz

FROM docker.io/library/debian:bookworm-slim AS runtime

LABEL org.opencontainers.image.source="https://github.com/AFAskar/MPMPAcrobatLinux" \
      org.opencontainers.image.description="MPMB Character Sheet Native Reader web server (PWA + QuickJS + PDFium)" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      fontconfig \
      fonts-dejavu-core \
      git \
      openssh-client \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 mpmb \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/sh mpmb \
    && mkdir -p /usr/lib/mpmb-reader /usr/share/licenses/mpmb-reader /data/sheets \
    && chown -R mpmb:mpmb /data

COPY --from=builder /src/target/release/mpmb-reader /usr/local/bin/mpmb-reader
COPY --from=builder /pdfium/lib/libpdfium.so /usr/lib/mpmb-reader/libpdfium.so
COPY --from=builder /pdfium/LICENSE /usr/share/licenses/mpmb-reader/PDFIUM-LICENSE

ENV MPMB_PDFIUM=/usr/lib/mpmb-reader/libpdfium.so \
    MPMB_DATA_DIR=/data/sheets \
    MPMB_SERVE_BIND=0.0.0.0:8080

USER 1000:1000
WORKDIR /data
EXPOSE 8080

ENTRYPOINT ["/usr/local/bin/mpmb-reader", "serve"]
