# cubi-agent web demo. Build: docker build -t cubi-agent .
# Run:   docker run -p 8080:8080 -e NEBIUS_API_KEY=... [-e TAVILY_API_KEY=...] [-e CUBI_MCP_TOKEN=...] cubi-agent
FROM python:3.12-slim
# The commit this image was built from, shown on /api/health (CI passes it).
ARG GIT_SHA=dev

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    # Behind the platform's HTTPS proxy: the client is the first X-Forwarded-For hop.
    TRUST_PROXY=1 PORT=8080 CUBI_AGENT_BUILD=${GIT_SHA}

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY agent ./agent
COPY web ./web
COPY skills ./skills
COPY vendor/cubi-estate-plugin/skills ./vendor/cubi-estate-plugin/skills
COPY vendor/cubi-estate-plugin/LICENSE ./vendor/cubi-estate-plugin/LICENSE
COPY fixtures/mcp_tools.json ./fixtures/mcp_tools.json
COPY fixtures/mcp ./fixtures/mcp
COPY LICENSE README.md ./

RUN useradd --uid 10001 --no-create-home app
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request,os; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8080\")}/api/health', timeout=4)"
CMD ["sh", "-c", "exec uvicorn agent.server:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*' --workers 1"]
