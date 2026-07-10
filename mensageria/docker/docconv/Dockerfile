# Imagem do conversor de documentos usada por app/documents/converter.py.
# Roda descartável: um container por conversão, sem rede, com teto de memória.
#
#   docker build -t docconv:1 docker/docconv
#
# Picos medidos (2026-07-10): soffice ~153 MB, pdf2docx ~96 MB.
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
      libreoffice-writer \
      libreoffice-calc \
      fonts-dejavu-core \
      fonts-liberation2 \
      python3 \
      python3-pip \
    && pip3 install --no-cache-dir --break-system-packages pdf2docx \
    && apt-get purge -y python3-pip \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/* /root/.cache

WORKDIR /work
