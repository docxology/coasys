# Architecture

The Typer command line and FastAPI API call the same operations service.
Git metadata and execution records are stored in SQLite, and the API
serves the static dashboard. Repository inspection applies Git’s local
checkout and clone model [@git-clone]. The persistence layer uses SQLite's
embedded database model [@sqlite-about], and the service serves its
browser assets through FastAPI’s static file support [@fastapi-static].

The service distinguishes detected commands from configured playbooks.
Detection inventories available commands. Gated profiles require an
explicit playbook and operator action. A real deploy additionally requires
the configured environment and a prior successful dry run. The reports
derive fleet and run status from the local store.

The installed executable and its commands are defined in
`src/coasys_ops/cli.py`. The service and persistence boundaries are in
`src/coasys_ops/ops.py` and `src/coasys_ops/store.py`.
