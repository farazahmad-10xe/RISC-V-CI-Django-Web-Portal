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

## Apollo production layout

```text
/opt/riscv-ci-portal       application checkout
/etc/riscv-ci-portal.env  secrets and environment configuration
/srv/riscv-results        compact reports and downloadable artifacts
/var/lib/pgsql             PostgreSQL-managed database files
```

Production installation is intentionally a separate step after local validation. Use `deploy/apollo.env.example`, `deploy/riscv-portal.service`, and `deploy/nginx-portal-location.conf` as reviewed templates. Do not commit real passwords or tokens.

The portal runs on `127.0.0.1:8090`; the existing Apollo Nginx service exposes it at `https://192.168.100.150/portal/`. Jenkins remains at the root URL.
