# Plan: Flux Map Improvements + Fluxer Integration

## 1. Improve the built-in Plotly flux map

- **Fix metabolite-name mapping bug.** The current manual central-carbon layout forces every measured feature into a hardcoded central-carbon node, which causes `PG(14:0)` to be labeled as `Glucose-6-phosphate`. I will switch to exact curated metabolite lookup first; if there is no curated match, the node will keep the original lipid/compound name and be grouped/colored by lipid class (e.g. LPC, PC, PE, SM, TAG).
- **Add layout options.** Expose Spring, Kamada-Kawai, Fruchterman-Reingold, Circular, and Grid layouts in the UI, with a fixed random seed so the same dataset renders identically each time.
- **Better visual styling.** Larger default height (700 px), responsive autosize, directed edges with arrowheads, node size mapped to total intensity (10–50 px), edge width mapped to label gradient/flux, text labels with a subtle halo to avoid overlap, and a discrete color legend by pathway/lipid class.
- **New UI toggles.** Show/hide node labels, show/hide reaction labels, color nodes by mean labeled atoms or by total intensity, scale node/edge sizes.
- **Rich hover info.** Lipid/compound name, formula, total intensity, mean labeled atoms, top M+n fraction, and pathway/lipid class.
- **Regression tests.** Unit tests for each layout, graph mode, and lipid-class fallback.

## 2. Add a Fluxer integration/export option

- **Research Fluxer API.** `fluxer.umbc.edu` is a web application that visualizes SBML/GEM models. I will check whether it exposes a public upload/link endpoint. If yes, I will implement an "Open in Fluxer" button for the currently selected GEM.
- **Fallback export.** If no direct API exists, I will add an "Export for Fluxer" option that downloads the current flux network as GraphML and, if a GEM is selected, the GEM as SBML. I will also add a help link to `https://fluxer.umbc.edu/` with upload instructions.
- **Fluxer-style view inside the app.** I will add a new "Fluxer" style preset to the built-in Plotly graph that uses a spanning-tree/k-shortest-path layout with a clean light palette, matching the Fluxer paper's default visualization style.
- **Tests.** Verify exported GraphML contains the expected nodes/edges and that the Fluxer-style preset renders without errors.

## 3. Testing & validation

- `python -m pytest -q`
- `npm run build`
- `npm run lint`
- Manual browser test on the existing El-MAVEN isotope dataset: generate flux map, switch layouts, toggle labels, export network.
- Check that existing isotope, preprocessing, and QC features still work.

## Open questions

- Should I implement a live "Open in Fluxer" link (needs investigation of their API), or is "Export GraphML/SBML" sufficient?
- Would you like an additional Sankey/flow-diagram view as an alternative to the network graph?
- Which lipid class groupings should be used as pathways in the legend? (I will reuse existing class parsing from `flux_map.py`.)
