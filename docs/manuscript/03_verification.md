# Verification and limitations

The repository tests use controlled inputs. The Git tests create local
repositories and check real cloning and inspection behavior. The API
tests use temporary application state to verify JSON responses and reject
stale document saves. Weave tests check dependency ordering, cyclic
graphs, canonical save/load behavior, and deployment eligibility when
prerequisites are absent.

These checks describe behavior under the fixtures in `tests/`. A
historical handoff snapshot records one fleet workspace. Current counts
depend on the local inventory and change as repositories are refreshed.
The release gate assumes that populated snapshot and uses a temporary
local dashboard server. A clean checkout can reproduce the native test
suite and this manuscript without cloning the fleet or running a deploy.

The screenshot illustrates the shipped interface. It is a documentation
asset and supplies no quantitative evaluation of operator outcomes.
