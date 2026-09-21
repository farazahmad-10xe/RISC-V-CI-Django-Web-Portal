# RISC-V CI Results Portal

Dynamic reporting for ACT executions on VisionFive 2, Banana Pi F3, and future RISC-V boards. The same source tree runs locally with SQLite and on Apollo with PostgreSQL.

## Local development

```bash
cd riscv_ci_portal
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py seed_demo
uv run python manage.py runserver 127.0.0.1:8090
```

Open `http://127.0.0.1:8090/portal/` and sign in.

Run validation with:

```bash
uv run python manage.py test
uv run ruff check .
```

## Result ingestion

Jenkins publishes a JSON document to `POST /portal/api/v1/runs/` with the token in `X-Portal-Token`. Reposting the same job and build number safely updates the run.

Minimal example:

```json
{
  "board": {"slug": "vf2", "name": "VisionFive 2", "core_profile": "SiFive U74"},
  "job": {"name": "vf2-privileged-weekly", "jenkins_url": "https://192.168.100.150/job/vf2-privileged-weekly/"},
  "build_number": 3,
  "status": "RUNNING",
  "expected_cases": 485,
  "completed_cases": 6,
  "passed_cases": 5,
  "failed_cases": 1,
  "results": [
    {
      "name": "ExceptionsM-01",
      "category": "Privileged",
      "extension": "ExceptionsM",
      "sail_status": "PASS",
      "spike_status": "SKIPPED",
      "hardware_status": "PASS"
    }
  ],
  "artifacts": [
    {
      "name": "test_status_matrix.xlsx",
      "relative_path": "vf2/vf2-privileged-weekly/3/test_status_matrix.xlsx",
      "kind": "excel"
    }
  ]
}
```

Files are stored below `PORTAL_ARTIFACT_ROOT`; only their metadata and relative paths are stored in PostgreSQL.

### Jenkins publisher

`tools/publish_jenkins_results.py` reads the runner's existing files directly:

- `state.env` for run identity and expected count
- `sail_reference_status.tsv` and `spike_status.tsv` for model results
- `cases.json` for hardware PASS/FAIL and failure details
- an optional reference workbook for the full expected suite inventory

It merges them into one idempotent API update. Store the ingest token in Jenkins as a
Secret Text credential named `riscv-portal-ingest-token`, then call the publisher from a
Declarative Pipeline `post { always { ... } }` block so failed and aborted runs are also reported:

```groovy
script {
  withEnv(["PORTAL_BUILD_RESULT=${currentBuild.currentResult}"]) {
    withCredentials([string(credentialsId: 'riscv-portal-ingest-token', variable: 'PORTAL_INGEST_TOKEN')]) {
      sh '''python3 "$PORTAL_PUBLISHER" \
        --state-root "$STATE_ROOT" \
        --run-root "$RUN_ROOT" \
        --board-slug vf2 \
        --board-name "VisionFive 2" \
        --core-profile "SiFive U74" \
        --job-name "$JOB_NAME" \
        --build-number "$BUILD_NUMBER" \
        --build-url "$BUILD_URL" \
        --status "$PORTAL_BUILD_RESULT" \
        --suite-inventory-xlsx /home/lpt-10xe/jenkins-agent/reference/vf2-suite-inventory.xlsx \
        --portal-url https://192.168.100.150/portal/ \
        --ca-file /etc/ssl/certs/jenkins-internal-ca.crt'''
    }
  }
}
```

Set `PORTAL_PUBLISHER`, `STATE_ROOT`, and `RUN_ROOT` to stable absolute paths on the
hardware agent. Do not read the token from a workspace file or place it in job XML.

Use `--no-post --output payload.json` to validate a job's mapping without changing the portal.

Pass `--artifact-store /home/lpt-10xe/jenkins-hardware-staging/portal-results` to retain
the compact run artifacts and each test's UART log in a build-numbered permanent directory
on the hardware agent. Privileged per-test UART logs are also gzip-compressed during upload,
stored below `PORTAL_ARTIFACT_ROOT` on Apollo, and served through authenticated portal links.

Use `--suite-inventory-xlsx` with a validated prior report to preserve the complete expected
suite when a current run stops early or does not generate a workbook. Tests absent from the
current run are published as `UNKNOWN` and counted as not run; they are never treated as passes.

## Apollo production layout

```text
/opt/riscv-ci-portal       application checkout
/etc/riscv-ci-portal.env  secrets and environment configuration
/srv/riscv-results        compact reports and downloadable artifacts
/var/lib/pgsql             PostgreSQL-managed database files
```

Production installation is intentionally a separate step after local validation. Use `deploy/apollo.env.example`, `deploy/riscv-portal.service`, and `deploy/nginx-portal-location.conf` as reviewed templates. Do not commit real passwords or tokens.

The portal runs on `127.0.0.1:8090`; the existing Apollo Nginx service exposes it at `https://192.168.100.150/portal/`. Jenkins remains at the root URL.
