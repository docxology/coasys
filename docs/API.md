# API Reference

The API is served by FastAPI through:

```bash
uv run coasys serve --host 127.0.0.1 --port 5050
```

There is no authentication layer in this local-first release. Bind to
`127.0.0.1` unless you intentionally expose it on another interface.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/summary` | Fleet counts and derived status totals. |
| `GET` | `/api/repos` | List all repositories. |
| `GET` | `/api/repos/{name}` | Repository detail plus recent runs for that repo. |
| `POST` | `/api/repos/{name}/sync` | Refresh one repository from GitHub and local Git. |
| `POST` | `/api/repos/{name}/validate` | Validate one repository. |
| `POST` | `/api/repos/{name}/run/{profile}` | Run one configured profile. |
| `POST` | `/api/operate` | Run fleet operation flow. |
| `GET` | `/api/runs` | List recent runs. |
| `GET` | `/api/runs/{id}` | Fetch one run record. |
| `GET` | `/api/report` | Return the Markdown operations report. |

## Summary

```bash
curl -fsS http://127.0.0.1:5050/api/summary
```

Representative fields:

```json
{
  "repo_count": 98,
  "cloned_count": 98,
  "dirty_count": 0,
  "behind_count": 0,
  "command_count": 328,
  "tiers": {"core": 7},
  "statuses": {"passed": 94, "warn": 4},
  "config_statuses": {"configured": 11, "detected": 84, "unconfigured": 3},
  "deploy_statuses": {"deploy_blocked": 94, "detected": 4}
}
```

## Repository List

```bash
curl -fsS http://127.0.0.1:5050/api/repos
```

Response shape:

```json
{
  "count": 98,
  "repos": [
    {
      "name": "ad4m",
      "tier": "core",
      "local_path": "workspace/repos/ad4m",
      "clone_status": "cloned",
      "config_status": "configured",
      "validation_status": "passed",
      "start_status": "dry_run_passed",
      "deploy_status": "deploy_blocked",
      "deploy_reason": "no deploy playbook configured",
      "next_action": "monitor"
    }
  ]
}
```

Raw GitHub payloads are removed from public API responses.

## Repository Detail

```bash
curl -fsS http://127.0.0.1:5050/api/repos/ad4m
```

The response contains:

- `repo`: decorated repository state.
- `runs`: recent run records for the repository.

Unknown repositories return `404`.

## Sync and Validate

```bash
curl -X POST http://127.0.0.1:5050/api/repos/ad4m/sync
curl -X POST 'http://127.0.0.1:5050/api/repos/ad4m/validate?execute_detected=false'
```

Validation with `execute_detected=true` can run detected commands beyond
automatic checks. Use it intentionally.

## Run Profile

```bash
curl -X POST 'http://127.0.0.1:5050/api/repos/ad4m/run/start?dry_run=true'
curl -X POST 'http://127.0.0.1:5050/api/repos/paperclip/run/deploy?dry_run=true'
```

Parameters:

| Parameter | Type | Meaning |
| --- | --- | --- |
| `dry_run` | boolean | Run readiness commands for the configured playbook. |
| `execute` | boolean | Run configured commands. Mutually exclusive with `dry_run`. |

Invalid profile requests return `400`, including:

- gated profile without explicit playbook,
- missing cloned checkout,
- missing required environment for execution,
- deploy execution without a passing dry run.

## Operate

```bash
curl -X POST 'http://127.0.0.1:5050/api/operate?clone=true&validate=true&tier=core'
curl -X POST 'http://127.0.0.1:5050/api/operate?execute_configured=true&tier=core'
```

Use `deploy=true` only for deploy dry-run readiness. Real deploy execution
requires `execute_deploy=true`, explicit playbooks, required environment, and
operator approval.

## Runs

```bash
curl -fsS 'http://127.0.0.1:5050/api/runs?limit=50'
curl -fsS http://127.0.0.1:5050/api/runs/1
```

Run records include:

- `id`
- `repo_name`
- `kind`
- `profile`
- `status`
- `exit_code`
- timestamps
- command argv list
- output tail
- log path

## Report

```bash
curl -fsS http://127.0.0.1:5050/api/report
```

The response is Markdown with media type `text/markdown`.

