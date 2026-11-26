# Weave documents and planning

The Weave loader accepts the original `coasys.yml` and the richer
`coasys.weave.yml`. The model represents repository dependencies,
environments, and application bindings in one document. Semantic
validation catches missing and cyclic repository dependencies. The graph
provides dependency-ordered waves for planning and a visual overview in
the dashboard, as shown in [@fig:weave-topology].

![Coasys Weave topology with tier-colored repository nodes and edges showing their dependencies.](../../output/figures/weave-graph.png){#fig:weave-topology}

The planning API derives readiness from the configuration and available
environment variable names. The runtime `operate` command still consumes
`coasys.yml`. Weave can export compatible operator configuration.

The dashboard saves validated documents atomically through
`POST /api/weave/document`. When a client supplies an older file hash,
the API returns a conflict before writing. The Onboard API registers an
entry and returns the proposed scaffold command for the operator.
