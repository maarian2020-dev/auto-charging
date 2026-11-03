FROM ghcr.io/home-assistant/base:latest

# Rama o etiqueta del repositorio que se instala (se puede fijar a una version, p. ej. v0.3.0)
ARG ALC_REF=main

RUN apk add --no-cache python3 py3-pip git \
    && pip install --no-cache-dir --break-system-packages \
       "git+https://github.com/maarian2020-dev/auto-charging.git@${ALC_REF}" \
    && apk del git

COPY run.sh /run.sh
RUN chmod a+x /run.sh

CMD ["/run.sh"]
