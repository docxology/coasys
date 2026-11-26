# Render the software manuscript

The numbered source, configuration, bibliography, and figure registry
live in [docs/manuscript/](manuscript/README.md).

Install Git, uv, Pandoc 3.1.11.1, the matching
[pandoc-crossref release](https://github.com/lierdakil/pandoc-crossref/releases/tag/v0.3.17.0c),
and XeLaTeX with the packages in the
[template run guide](https://github.com/docxology/template/blob/87704feae0a4490ef7dad9c931d268e8c30273c2/docs/RUN_GUIDE.md).
Start at the root of a clean Coasys Ops checkout:

```sh
coasys_checkout="$PWD"
mkdir -p output/figures
cp docs/images/weave-graph.png output/figures/
cp docs/manuscript/figure_registry.json output/figures/

git clone https://github.com/docxology/template.git ../coasys-renderer
cd ../coasys-renderer
git checkout --detach 87704feae0a4490ef7dad9c931d268e8c30273c2
uv sync --locked --no-dev
mkdir -p projects/working
ln -s "$coasys_checkout" "projects/working/$(basename "$coasys_checkout")"
coasys_project="working/$(basename "$coasys_checkout")"
uv run --no-sync python scripts/pipeline/stage_03_render.py --project "$coasys_project"
uv run --no-sync python scripts/pipeline/stage_04_validate.py --project "$coasys_project"
```

The runner discovers the manuscript under `docs/manuscript/` and reads
its configuration and bibliography there. It resolves the screenshot
from the generated `output/figures/` copy. Stage 04 requires indexed
source files for provenance.

From the Coasys checkout, find the combined PDF under `output/pdf/`,
the HTML at `output/web/index.html`, and validation and provenance reports
under `output/reports/`. Check the section order, cited sources, and
Weave topology figure in the combined outputs.
