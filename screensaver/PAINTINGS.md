# Campus paintings

The home view is a painting of DGIST, picked every half hour from DGIST's sun, weather and date (`campus_painted.py`):

| light | when |
|---|---|
| night | sun below −6° |
| dusk | −6° to 2° (dawn too) |
| golden | 2° to 12° |
| day | above 12° |
| overcast | day or golden with cloud ≥ 80 %, rain, fog or (outside winter) snow |
| snow | winter, day or golden, snowing |

Seasons: autumn 12 Oct–28 Nov, winter 29 Nov–10 Mar, spring 11 Mar–10 May, summer the rest.
Rain and snow fall on top of any painting; the shuttle, walkers and the pin are drawn from `paintings/geometry.json`.

## Remaking the set

The paintings are made on a PC, not in Actions. From the project folder that holds this repo:

1. `python sim/render_variants.py`: renders the 3D campus (`render3d/`, three.js in headless Chrome) for every season and light. Set `CAMPUS_GL=d3d11` to use the GPU on Windows. Run `npm ci` in `render3d/` first.
2. `python sim/codex_paint.py <names…>`: Codex image generation repaints each render in the style of the two reference paintings (the film-background style chosen on 4 Nov 2026).
3. `python sim/build_paintings.py --quality 55`: encodes `paintings/<season>-<light>.avif` (1320×742, about 60–110 KB each) and writes `geometry.json`.

The camera, the crop (`crop` in `geometry.json`) and the building anchors must stay the same between the render and the paintings, or the pin will miss its building.
