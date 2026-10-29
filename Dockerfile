FROM node:22-alpine AS assets
WORKDIR /build
COPY package.json yarn.lock ./
RUN yarn install --frozen-lockfile
COPY tailwind.config.js ./
COPY scripts/copy-vendor.mjs ./scripts/copy-vendor.mjs
COPY app/static ./app/static
RUN yarn build

FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --create-home --uid 10001 cst
COPY app ./app
COPY context ./context
COPY sources/formulas.pdf ./sources/formulas.pdf
COPY --from=assets /build/app/static /app/app/static
USER cst
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=30s --retries=5 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
