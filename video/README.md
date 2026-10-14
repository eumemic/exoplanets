# Explainer video

A 223-second explainer of the TESS search, made for posting on X: narration (ElevenLabs), music ("Percolating Cosmos",
Suno), and a picture built in Remotion from the repository's own data. `SCRIPT.md` has the brief and
narration, `STORYBOARD.md` the original plan.

## Recreating the film

Git holds the code and the small data files. The binaries are in the
[`explainer-v9` release](https://github.com/eumemic/exoplanets/releases/tag/explainer-v9):
`video-assets.tar.gz` (the 4-million-star sky, the final mix, and the narration clips and music the mix is built
from) and the finished film. With Node 20 or later, ffmpeg and a GPU:

```bash
cd video
npm install
tools/fetch_assets.sh                  # unpacks the release's binaries here
REMOTION_FPS=60 npx remotion render src/index.ts Film out/video.mp4 --gl=angle --muted --x264-preset=slow --color-space=bt709 --crf=16
ffmpeg -i out/video.mp4 -i public/audio/mix.m4a -map 0:v -map 1:a -c copy -movflags +faststart out/exoplanets_explainer.mp4
```

The narration is an ElevenLabs voice ("Allison", from its voice library). The music, "Percolating Cosmos", was
made with Suno for this film and is for non-commercial use.

## Audio

`tools/narration.py` records the first cut's narration and `tools/stretch_vo.py` speeds it up 4%;
`tools/narration_v2.py` and `tools/narration_v3.py` record the rewrites of the second and third cuts.
`tools/mix.py` made the first cut's mix (`cut_allison_v6`). `tools/mix2.py` cuts the narration into
phrases at the pauses between sentences, places them with pauses the visuals need, edits the music to fit,
and writes the mix (`audio/mix/cut_allison_v13.m4a` for v9: v8 with the count updated to 546, two lines re-recorded by
`tools/narration_v5.py`) and `timeline.json`, which the
picture is timed to. `tools/check_take.py` lists the pauses in a take; `tools/stt_check.py` transcribes
every cut phrase to confirm that no cut clips a word.

## Data

Prepared with the repository's Python environment (`.venv` at its root), from its catalogs, results and stored
light curves (the catalogs and light curves are local, not in git; the prepared files are, or are in the release):

| Script | Writes | What |
|---|---|---|
| `tools/searched_stars.py` | `data/searched_tics.npy` | the 4,039,203 stars the full-sky search searched |
| `tools/prep_sky.py` | `public/data/sky.bin` | their ecliptic positions, T magnitudes and temperatures |
| `tools/prep_points.py` | `public/data/points.json` | the 546 candidates (438 full-sky, 50 tier L1, 58 earlier) |
| `tools/prep_lc.py` | `public/data/lc.json` | TIC 4206066, the validation stars, L 98-59, a flipped false alarm, an eclipsing binary |
| `tools/prep_tess.py` | `public/data/tess.json` | TESS sector footprints for Sectors 1-104 (tess-point) |
| `tools/prep_periodogram.py` | `public/data/periodogram.json` | a BLS periodogram of TIC 4206066 |
| `tools/prep_pixels.py` | `public/data/pixels_*.json` | difference images; the film uses TIC 127236638, Sector 44 |
| `tools/prep_words.py` | `src/data/*.json` | word timings and caption chunks from the narration alignment |

## Picture

`src/Film.tsx` stacks the scenes in `src/scenes/`. `SkyGL.tsx` draws all 4 million stars with three.js
(globe, map and dome projections, plus the candidate layer); `skyDirector.ts` sets its state over time,
and `times.ts` ties scene times to words in the narration.

```bash
npm install
npx remotion studio src/index.ts                                   # preview
REMOTION_FPS=30 npx remotion render src/index.ts Film out/draft.mp4 --gl=angle
REMOTION_FPS=60 npx remotion render src/index.ts Film out/video.mp4 --gl=angle --muted --x264-preset=slow --color-space=bt709 --crf=16
ffmpeg -i out/video.mp4 -i audio/mix/cut_allison_v13.m4a -map 0:v -map 1:a -c copy -movflags +faststart out/exoplanets_explainer.mp4
```

On an M4 Pro the 60 fps render takes 10 to 15 minutes.

Checks: `tools/flicker_audit.py VIDEO` finds regions that jump for one frame and back; `tools/label_audit.py VIDEO`
measures how still the labels are; `tools/stills.py` renders stills at given times into one sheet. Do not put CSS transforms on elements that contain text: headless Chrome
sometimes drops them in single frames, which makes labels jump.

### 3D shots

Two shots are real 3D scenes, built from the pieces in `src/lib/space3d.ts` (star and planet shaders, glare, orbit
lines, star field, camera rig): `Field3D.tsx`, a thick sheet of star systems at random tilts that the camera drifts
across and then pulls far back from, where the lined-up ones turn bold gold while the rest dim; and
`Rabtsevich3D.tsx`, his star reached along our line of sight (so its two orbits are edge-on) before the camera rises
over them. v5's flat versions of both are in `_old/v5_scenes/`. Others were tried against the flat shots, side by
side, and dropped: the opening as a flight out of the 4 million stars at their TIC distances (it read as a collapse
and re-expansion), the primer as a close-up of a planet coming down to edge-on (the flat shot was better), TESS's
sweep painted on a celestial globe around Earth (the cut from the field to a sphere around Earth did not follow),
and the result opening into space with each candidate at its distance (a distraction).

Changes under review are experiments: a flag in `src/lab.ts` switches each on (the `lab` prop of `Film`; the
`Lab*` compositions have one on each). `tools/compare.py` makes the review clips: `stack` puts the current cut
over the change, in step (for a picture change); `seq` plays one after the other, each with its own sound (for a
narration change). New narration lines are recorded in several takes (`tools/narration_v4.py`) and the one closest
to the line it replaces in pace, loudness and pitch is chosen (`tools/compare_takes.py`); v6's timing data is kept
in `audio/mix/timeline_v9.json` and `src/data/_v9/`.

A 3D canvas is drawn with `mix-blend-mode: screen` onto the sky behind it. Give it its own opacity, never a
translucent wrapper: that isolates it, so its black background covers the sky instead (seen as the sky darkening
while the layer fades, then snapping back). `tools/compare_frames.py` compares stills with a rendered video, to
confirm that a change leaves the rest of the film alone.
