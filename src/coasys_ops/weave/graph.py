"""The Weave graph: the formal backbone of the *visual* language.

A Weave document denotes a typed multigraph. The visual surface (the dashboard
graph view) renders exactly this structure, and the operations planner consumes
its topological layering ("waves"). Keeping a single graph builder guarantees
the picture and the execution order never diverge.

Node kinds: ``repo``, ``seed``, ``environment``.
Edge kinds:
  - ``needs``        repo -> repo   (build/operate ordering)
  - ``deploy-needs`` repo -> repo   (deploy ordering, from playbooks.deploy.needs)
  - ``uses``         seed -> repo   (design: a launcher embeds a repo's WE app)
  - ``deploy-to``    repo -> env    (a deploy playbook targets an environment)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .model import WeaveDocument


@dataclass
class Node:
    id: str
    kind: str
    label: str
    tier: str | None = None
    attrs: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "label": self.label,
            "tier": self.tier,
            **self.attrs,
        }


@dataclass
class Edge:
    source: str
    target: str
    kind: str

    def to_dict(self) -> dict[str, Any]:
        return {"source": self.source, "target": self.target, "kind": self.kind}


@dataclass
class Graph:
    nodes: list[Node]
    edges: list[Edge]
    build_waves: list[list[str]]
    deploy_waves: list[list[str]]
    targets: list[str]
    cycles: list[list[str]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
            "build_waves": self.build_waves,
            "deploy_waves": self.deploy_waves,
            "targets": self.targets,
            "cycles": self.cycles,
        }


def _node_id(kind: str, name: str) -> str:
    return f"{kind}:{name}"


def _toposort(
    nodes: list[str], deps: dict[str, list[str]]
) -> tuple[list[list[str]], list[list[str]]]:
    """Kahn layering. Returns (waves, cycles).

    Each wave is a set of nodes whose dependencies are all satisfied by earlier
    waves. Nodes that never resolve are reported as the residual cycle set.
    """
    remaining = {name: [d for d in deps.get(name, []) if d in nodes] for name in nodes}
    waves: list[list[str]] = []
    placed: set[str] = set()
    while True:
        layer = sorted(
            name
            for name, ds in remaining.items()
            if name not in placed and all(d in placed for d in ds)
        )
        if not layer:
            break
        waves.append(layer)
        placed.update(layer)
    leftover = sorted(name for name in nodes if name not in placed)
    cycles = [leftover] if leftover else []
    return waves, cycles


def build_graph(document: WeaveDocument) -> Graph:
    nodes: list[Node] = []
    edges: list[Edge] = []

    repo_names = set(document.repos)

    # Repo nodes.
    for name, repo in document.repos.items():
        has_deploy = "deploy" in repo.playbooks
        nodes.append(
            Node(
                id=_node_id("repo", name),
                kind="repo",
                label=name,
                tier=repo.tier,
                attrs={
                    "target": repo.target or repo.tier == "core",
                    "priority": repo.priority,
                    "stack": repo.stack,
                    "profiles": sorted(repo.playbooks),
                    "has_we_app": bool(repo.we and repo.we.app),
                    "deployable": has_deploy,
                },
            )
        )

    # Environment nodes.
    for name, env in document.environments.items():
        nodes.append(
            Node(
                id=_node_id("env", name),
                kind="environment",
                label=name,
                attrs={"protected": env.protected, "requires_env": env.requires_env},
            )
        )

    # Seed nodes.
    for name, seed in document.seeds.items():
        nodes.append(
            Node(
                id=_node_id("seed", name),
                kind="seed",
                label=name,
                attrs={"project": seed.project.name, "app_count": len(seed.apps)},
            )
        )

    # Build-ordering and deploy-ordering edges.
    build_deps: dict[str, list[str]] = {name: [] for name in document.repos}
    deploy_deps: dict[str, list[str]] = {}
    for name, repo in document.repos.items():
        for dep in repo.needs:
            if dep in repo_names:
                edges.append(Edge(_node_id("repo", dep), _node_id("repo", name), "needs"))
                build_deps[name].append(dep)
        deploy_pb = repo.playbooks.get("deploy")
        if deploy_pb is not None:
            deploy_deps[name] = []
            for dep in deploy_pb.needs:
                if dep in repo_names:
                    edges.append(
                        Edge(_node_id("repo", dep), _node_id("repo", name), "deploy-needs")
                    )
                    deploy_deps[name].append(dep)
            if deploy_pb.environment and deploy_pb.environment in document.environments:
                edges.append(
                    Edge(
                        _node_id("repo", name),
                        _node_id("env", deploy_pb.environment),
                        "deploy-to",
                    )
                )

    # Design edges: seeds embed repo WE apps.
    for seed_name, seed in document.seeds.items():
        for app in seed.apps:
            if app.use and app.use in repo_names:
                edges.append(
                    Edge(_node_id("seed", seed_name), _node_id("repo", app.use), "uses")
                )

    build_waves, build_cycles = _toposort(list(document.repos), build_deps)
    deploy_waves, deploy_cycles = _toposort(list(deploy_deps), deploy_deps)

    return Graph(
        nodes=nodes,
        edges=edges,
        build_waves=build_waves,
        deploy_waves=deploy_waves,
        targets=document.targets(),
        cycles=build_cycles + deploy_cycles,
    )


def to_mermaid(document: WeaveDocument) -> str:
    """Render the build/deploy/design graph as a Mermaid ``graph LR`` block."""
    graph = build_graph(document)
    tier_class = {
        "core": "core",
        "active": "active",
        "language": "language",
        "dependency-fork": "fork",
        "stale": "stale",
    }
    lines = ["graph LR"]
    for node in graph.nodes:
        nid = node.id.replace(":", "_").replace("-", "_")
        if node.kind == "repo":
            lines.append(f'  {nid}["{node.label}"]')
            cls = tier_class.get(node.tier or "", "")
            if cls:
                lines.append(f"  class {nid} {cls};")
        elif node.kind == "environment":
            lines.append(f'  {nid}{{{{"{node.label}"}}}}')
        else:
            lines.append(f'  {nid}[/"{node.label}"/]')
    arrow = {"needs": "-->", "deploy-needs": "-.->", "uses": "==>", "deploy-to": "-->"}
    for edge in graph.edges:
        src = edge.source.replace(":", "_").replace("-", "_")
        tgt = edge.target.replace(":", "_").replace("-", "_")
        lines.append(f"  {src} {arrow.get(edge.kind, '-->')} {tgt}")
    lines += [
        "  classDef core fill:#5b8def,stroke:#2c4a8a,color:#fff;",
        "  classDef active fill:#34c759,stroke:#1c7a33,color:#fff;",
        "  classDef language fill:#af52de,stroke:#6a2c8a,color:#fff;",
        "  classDef fork fill:#8e8e93,stroke:#48484a,color:#fff;",
        "  classDef stale fill:#c7c7cc,stroke:#8e8e93,color:#333;",
    ]
    return "\n".join(lines)


def to_dot(document: WeaveDocument) -> str:
    """Render the graph as Graphviz DOT."""
    graph = build_graph(document)
    lines = ["digraph weave {", "  rankdir=LR;", '  node [shape=box, style=rounded];']
    for node in graph.nodes:
        shape = {"repo": "box", "environment": "hexagon", "seed": "parallelogram"}[node.kind]
        lines.append(f'  "{node.id}" [label="{node.label}", shape={shape}];')
    style = {"needs": "solid", "deploy-needs": "dashed", "uses": "bold", "deploy-to": "dotted"}
    for edge in graph.edges:
        lines.append(
            f'  "{edge.source}" -> "{edge.target}" [style={style.get(edge.kind, "solid")}];'
        )
    lines.append("}")
    return "\n".join(lines)
