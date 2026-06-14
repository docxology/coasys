"""The Weave language model.

These pydantic models define the *abstract syntax* of Weave. The concrete
syntax is YAML (``coasys.weave.yml``); the loader normalises both the native
Weave shape and the legacy ``coasys.yml`` shape into this model. The visual
language (graph + schema forms) is derived mechanically from this model, so the
model is the single source of truth for every surface.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# AD4M capabilities recognised by the WE launcher (see coasys/we seed-system).
CAPABILITIES = (
    "perspectives",
    "languages",
    "agents",
    "filesystem",
    "network",
)

# Fleet classification tiers (mirrors coasys_ops.classify).
KNOWN_TIERS = (
    "core",
    "active",
    "language",
    "dependency-fork",
    "stale",
    "unknown",
)

# Lifecycle profiles, in canonical execution order. ``setup`` is the
# bootstrapping phase (install toolchains/dependencies) that precedes the rest.
LIFECYCLE_PROFILES = ("setup", "validate", "build", "start", "deploy")


class WeaveBase(BaseModel):
    """Base model: forbid unknown keys so typos surface as validation errors."""

    model_config = ConfigDict(extra="forbid")


class CloneSpec(WeaveBase):
    protocol: str = "https"
    depth: int | None = 1
    partial: bool = True

    @field_validator("protocol")
    @classmethod
    def _protocol(cls, value: str) -> str:
        if value not in ("https", "ssh"):
            raise ValueError("clone.protocol must be 'https' or 'ssh'")
        return value


class Defaults(WeaveBase):
    timeout_seconds: int = 600
    clone: CloneSpec = Field(default_factory=CloneSpec)
    execute_detected_validation: bool = False
    # Default package manager for repos that do not declare one. The fleet uses
    # uv for python tooling and pnpm/npm/cargo for the JS/Rust members.
    package_manager: str = "uv"


class Workspace(WeaveBase):
    repos_dir: str = "workspace/repos"
    state_dir: str = "workspace/state"


class Meta(WeaveBase):
    name: str = "coasys-fleet"
    org: str = "coasys"
    description: str = ""


class Environment(WeaveBase):
    """A named deployment environment (e.g. staging, production)."""

    description: str = ""
    requires_env: list[str] = Field(default_factory=list)
    # Protected environments require an explicit operator decision to deploy.
    protected: bool = False


class Playbook(WeaveBase):
    """A lifecycle profile: the commands to run and how they are gated.

    ``run`` are the real commands; ``check`` are the cheap dry-run readiness
    commands. ``needs`` expresses *deploy ordering* edges between repos for the
    deploy profile (build ordering lives on :attr:`Repo.needs`).
    """

    run: list[str] = Field(default_factory=list)
    check: list[str] = Field(default_factory=list)
    env: list[str] = Field(default_factory=list)
    working_dir: str | None = None
    timeout_seconds: int | None = None
    automatic: bool = False
    allow_detected: bool = False
    environment: str | None = None
    needs: list[str] = Field(default_factory=list)


class DevServer(WeaveBase):
    port: int
    host: str = "localhost"


class AppPaths(WeaveBase):
    project_root: str | None = None
    dist: str | None = None
    dev_server: DevServer | None = None


class AppCommands(WeaveBase):
    install: str | None = None
    build: str | None = None
    dev: str | None = None


class WeApp(WeaveBase):
    """A WE-embeddable application, mirroring the seed-system app schema."""

    id: str
    name: str
    route: str = "/"
    capabilities: list[str] = Field(default_factory=list)
    paths: AppPaths | None = None
    commands: AppCommands | None = None

    @field_validator("capabilities")
    @classmethod
    def _capabilities(cls, value: list[str]) -> list[str]:
        for cap in value:
            if cap not in CAPABILITIES:
                raise ValueError(
                    f"unknown capability {cap!r}; expected one of {', '.join(CAPABILITIES)}"
                )
        return value


class WeBinding(WeaveBase):
    """The design-layer binding of a repo into the WE ecosystem."""

    app: WeApp | None = None


class RepoSource(WeaveBase):
    url: str | None = None
    clone_url: str | None = None
    branch: str | None = None


class Repo(WeaveBase):
    """A managed repository in the fleet."""

    tier: str | None = None
    # Priority targets are operated first; higher priority sorts earlier.
    target: bool = False
    priority: int = 0
    description: str = ""
    source: RepoSource | None = None
    stack: list[str] = Field(default_factory=list)
    # Build/operate ordering edges: this repo depends on these repos.
    needs: list[str] = Field(default_factory=list)
    env: list[str] = Field(default_factory=list)
    timeout_seconds: int | None = None
    playbooks: dict[str, Playbook] = Field(default_factory=dict)
    we: WeBinding | None = None


class SeedProject(WeaveBase):
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = "coasys"


class SeedApp(WeaveBase):
    """A reference to a repo's WE app (``use``) or an inline app definition."""

    use: str | None = None
    route: str | None = None  # override the repo's default route
    app: WeApp | None = None


class Seed(WeaveBase):
    """A WE launcher seed: compiles to a real ``we-seed.json``."""

    project: SeedProject
    host: dict[str, Any] = Field(default_factory=dict)
    ad4m: dict[str, Any] = Field(default_factory=dict)
    apps: list[SeedApp] = Field(default_factory=list)


class WeaveDocument(WeaveBase):
    """The root Weave document."""

    version: int = 1
    weave: Meta = Field(default_factory=Meta)
    workspace: Workspace = Field(default_factory=Workspace)
    defaults: Defaults = Field(default_factory=Defaults)
    environments: dict[str, Environment] = Field(default_factory=dict)
    seeds: dict[str, Seed] = Field(default_factory=dict)
    repos: dict[str, Repo] = Field(default_factory=dict)

    # -- convenience accessors -------------------------------------------------

    def targets(self) -> list[str]:
        """Repository names ordered as operation targets.

        Targets are repos explicitly marked ``target`` or in the ``core`` tier,
        ordered by descending priority then name. This realises "starting with
        the most important target ones".
        """

        def is_target(name: str, repo: Repo) -> bool:
            return repo.target or repo.tier == "core"

        chosen = [(name, repo) for name, repo in self.repos.items() if is_target(name, repo)]
        chosen.sort(key=lambda item: (-item[1].priority, item[0]))
        return [name for name, _ in chosen]

    def repo_names(self) -> list[str]:
        return sorted(self.repos)
