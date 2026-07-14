FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY app ./app
RUN pip install --no-cache-dir .
EXPOSE 8787
ENV ALG_HOST=127.0.0.1
CMD ["alg", "run", "--host", "0.0.0.0"]

