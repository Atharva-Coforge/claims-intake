# Claims Intake Service

The claims portal posts a first notice of loss here. The service checks it
against the policy master and the rule table in `docs/api-contract.md`. If every
rule passes, it records the notification and returns a claim reference. If a
rule fails, it refuses with a specific code and does not write a record.

Everything under `data/` is synthetic. There are no real clients.

You are already in the lab container. Dependencies were installed when the
container was created (`uv sync --frozen`). Do not install anything. If a
command below is missing, that is a defect in the image, not a step for you.

Confirm the environment, then move to the project directory (the folder that
contains `pyproject.toml` and `Dockerfile`):

```
uname -sm
pwd
```

## Run the service

From that directory:

```
uv run uvicorn claims.api.routes:app --host 0.0.0.0 --port 8000
```

`POST /notifications` is the only endpoint. A valid body is recorded as `201`
with a `claim_reference`. A refusal uses the error envelope in the contract.

## Run the tests

Still from that directory, no extra install:

```
uv run pytest
uv run ruff check .
uv run mypy src tests
```

Unit tests sit next to the code they pin. Integration tests in
`tests/integration/` go through HTTP.

## Run it in Docker, and why `--platform linux/amd64`

This container is often Linux on ARM (Apple Silicon). The lab grades a
`linux/amd64` image. If you build with no platform flag, Docker follows *this*
machine and you get an ARM image that works on your laptop and fails where it
is marked.

`--platform linux/amd64` names the CPU the image is for, so what you run is
what the grader runs.

Build from the directory that contains the `Dockerfile`:

```
docker buildx build --platform linux/amd64 -t claims-intake .
```

Then run that image and post to port 8000 the same way as above.
<!-- REVIEW: "the same way as above" adds a lookup step for readers. Could just repeat the actual docker run / curl command here for a self-contained flow, e.g.:
docker run -p 8000:8000 claims-intake
curl -X POST localhost:8000/...
-->
## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. |
| `docs/requirements-brief.md` | Work items and their acceptance criteria. |
| `data/` | Synthetic policies and notification payloads. |
| `src/claims/` | The service. |
| `tests/` | Unit tests and HTTP integration tests. |
