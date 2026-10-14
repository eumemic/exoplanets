# Storyboard (draft 1)

Times are from `timeline.json` (mix `cut_allison_v6`, 133.4 s). Every star, curve, count and pixel on screen is real data from the repo or from NASA's archive.

## Concept: the dip

One shape runs through the whole film: a line of starlight with a small notch in it, the signature of a transit. It is drawn from real data in each scene. It is the light curve in the primer, the stripe the winding fold reveals, a particle in the funnel, a bump after the flip, and the underline of the URL on the end card. Each transition carries an object across the cut (the kit's rule), usually the sky map or the line.

The sky map is the film's stage. All 4.04 million stars are drawn at their real positions and in their real colours (from the TIC temperatures; our targets are mostly orange K and M dwarfs). The Milky Way appears on its own, because star density traces the galaxy. The film returns to the map four times: for TESS's sweep, Rabtsevich's star, the known planets the search found again, and the 492 candidates.

## Design language

- **Palette.** Deep navy space, `#070B14` to `#0E1A2E`, never flat black.
  - Stars in their blackbody colours.
  - Instrument/data cyan `#5CE1E6` for light curves and readouts.
  - Candidate gold `#FFC857`.
  - Reject/false-alarm coral `#FF5D73`.
  - Earth blue `#4F9DFF`.
  - Text `#E8EEF6`, secondary `#8FA3BF`.
- **Type.** Space Grotesk for headlines and labels, JetBrains Mono for every number and counter (an instrument-readout feel). Both are open-licensed Google Fonts.
- **Captions.** Burned in, bottom centre, at most 2 lines at 46 px, word-timed from the narration alignment. Numbers appear as numerals ("492"). The safe area is kept clear of charts.
- **Motion.**
  - Each composition has a readable landing, then an accelerating exit.
  - Nothing holds still for more than 0.6 s: the camera always drifts slightly.
  - Easing is expo/cubic, never linear, except for data drawing in at constant speed.
  - Cuts and section hits land on music beats (107.7 BPM grid).
  - Bloom on light sources only.
  - Light film grain to keep the gradients from banding.

## Signature transformations

1. **The sky assembles.** Four million real stars stream in, brightest first, and the Milky Way forms.
2. **Winding the light curve.** Eight years of one star's brightness wrap around a cylinder whose circumference is the orbital period. At the wrong period the dips scatter; at the right one they line up into a single stripe. This is what a period search does, shown literally.
3. **The flip.** A light curve rotates 180° in 3D, so its dips become bumps. Noise wiggles still make small dips, and those glow coral as false alarms.
4. **Dots to sizes.** The 492 candidate dots lift off the sky and land on a size axis where the solar system's planets sit. They fill the empty stretch between Earth and Neptune.

## Scenes

| Time | Narration | Picture | Out (carried object) |
|---|---|---|---|
| 0.0–1.0 | (music fades in) | Frame 0 is already a composition: a few bright stars on deep navy, with slow parallax drift. | — |
| 1.0–5.8 | We searched four million stars for planets hiding in NASA's public data. | **Sky assembles** (Mollweide projection). The counter runs up to 4,039,203 in mono type. "NASA TESS · Sectors 1–104" fades in small. | The camera dives toward one orange star. |
| 7.3–15.7 | Exoplanets, planets around other stars, are lost in their stars' glare, so we can almost never see them directly. | That star fills the frame: a glowing disc with bloom and diffraction spikes. A tiny planet orbits inside the glare; a thin leader line and the label "planet" point to where it is lost. The pulse enters at 8.7 s, and the orbit's motion picks up its rhythm. | The camera swings to edge-on. |
| 15.7–21.0 | But when one passes in front of its star, the star dims, very slightly. | Edge-on: the planet's silhouette crosses the disc. Below, a cyan light curve draws in real time, dipping in step with the crossing. | The line stays and the star swaps out. |
| 21.0–25.4 | Earth would dim the Sun by less than one part in ten thousand. | The Sun with Earth to scale, 1/109 of its width. On a true 0–100% axis the dip is invisible. The y-axis then zooms ×1,000 and the 0.0084% notch appears: "1 part in 11,900 · 13 hours · once a year". | Pull back. |
| 25.4–32.0 | And only a few planets line up just right for us to see this, so you have to watch a lot of stars. | 3D: a field of about 100 star systems, each orbit tilted at random as it would be in nature. Seen from our viewpoint, only the handful whose orbits cross their star light up; the rest fade. The view pulls back to thousands. | The systems become points on the sky map. |
| 32.0–36.3 | Since 2018, NASA's TESS satellite has been doing just that. | TESS's real footprints (four cameras, a 24°×96° strip) sweep the sky sector by sector, Sector 1 → 104, with years 2018 → 2026 ticking. Each pass brightens what it covered, so the ecliptic poles end up brightest. | The sweep ends on Sector 98's strip. |
| 37.8–47.7 | This search was inspired by independent researcher Pavel Rabtsevich, who found two possible planets around a nearby star in TESS's newest data. | Zoom into Sector 98 to TIC 4206066 at its real position. Lower third: "Pavel Rabtsevich 2026 · doi:10.5281/zenodo.22967456". His star's Sector 98 light curve draws in. | His other sectors appear. |
| 47.7–56.8 | We took every star like the Sun or smaller, joined up to eight years of observations, and checked each one for dips that repeat on a regular schedule. | His star's real light curves from Sectors 6 (2018), 32 (2020) and 98 (2025) slide onto one timeline, joined. Then **winding**: the scattered 500 ppm dips line up into one stripe at 3.18 days, and a periodogram spike rises beside it. | The folded dip lifts off as a glyph. |
| 58.3–65.8 | That turned up seven and a half million signals, almost all of them noise, or pairs of stars eclipsing each other. | The glyph multiplies into a particle stream with a counter to 7,459,491. Two specimens pop out: a noise wiggle, and an eclipsing binary (deep V-shaped dip with a secondary eclipse). | The stream flows into gates. |
| 65.8–72.0 | So every signal had to pass seventeen statistical tests, then a pixel-level check: | The stream passes through 17 thin gates. Each one sheds coral sparks, and the counter falls 7,459,491 → 609,021 → 13,986 → 9,962. | One particle is pulled out. |
| 72.0–74.9 | is the dip really on our star, or on a neighbour? | A real TESS pixel cutout (21″ pixels). The difference image lights up the pixels that dimmed, and the centroid arrow swings from our star onto a neighbour, which is rejected. The counter lands on 432, with a small side branch for the crowded-field candidates rescued by TRICERATOPS. | Pull back to the sky. |
| 76.4–82.6 | How do we know the filter works? It finds known planets without being told where they are. | Sky map: the 3,829 known planets and TOIs the search found again light up in white, with a few labelled: TOI-700, L 98-59, and Rabtsevich's TIC 4206066. | One light curve lifts out of the map. |
| 82.6–95.9 | And we ran it on four hundred thousand stars with their data flipped upside down. Planets only ever make a star dimmer, so anything it finds there is a false alarm, and that tells us how many slip through. | **The flip.** The scanner sweeps flipped curves and flags noise dips in coral. Then the measured false-alarm rate by signal strength: about 50% for the weakest, 16%, then under 6%. A cut line drops at signal strength 10 and the weak ones fall away. | The chart collapses to a point. |
| 97.4–101.8 | The result: four hundred ninety-two planet candidates. | On the bass re-entry at 97.85 s, the sky map returns and 492 gold points ignite across it in a wave, with the counter at 492. | The dots lift off. |
| 101.8–110.0 | More than half are between the size of Earth and Neptune: the most common kind of planet in the galaxy, and one our solar system doesn't have. | **Dots to sizes.** The solar system's planets sit on a size axis (Mercury → Jupiter, true relative sizes) with an empty stretch between Earth (1.0) and Neptune (3.88). The 492 dots fly in and pile up, mostly in that stretch, which glows. | The dots return to the sky. |
| 112.5–121.5 | They're candidates, not confirmed planets. Everything here came from public data, and our code and every candidate are online. | Type: "Candidates, not confirmed planets." Then credits stack: "Data: NASA TESS via MAST" · "Code and catalog: github.com/eumemic/exoplanets". | The camera starts its last pull-back. |
| 121.5–129.2 | Now it's up to telescopes on the ground to find out which ones are real. | The sky map tilts into a dome over a simple observatory silhouette line drawing (illustration, not imagery), and a few gold candidates twinkle overhead. | The final chord. |
| 129.2–133.4 | (final chord rings out) | End card: the dip line draws across and underlines github.com/eumemic/exoplanets; "Eumemic" small. It holds while the music rings out. | — |

## Data for each scene

- **Sky map:** `data/catalogs/shard0-7.parquet` (4.17 M TIC rows: ra, dec, Teff, Tmag). Packed as Float32 positions and colours.
- **Candidates and known planets:** `results_public/candidates_allsky.csv`, `tiers_earlier_candidates.csv`, and the match tables, joined to the TIC for positions.
- **TESS footprints:** sector pointings from `tess-point`, with dates from `data/tess_schedule`.
- **Rabtsevich's star:** `data/samples_4206066` (QLP and SPOC light curves for Sectors 6, 32 and 98).
- **Pixel check:** a cutout from `data/followup_pixels` with a neighbour-caused signal, or one fresh TESScut cutout.
- **Funnel and false alarms:** README tables and `validation/false_alarms_inverted_798769_stars.csv`.
- **Radii:** the catalog's `Rp_Re`, plus the solar system's radii.

## Process

1. **Style frames** for sign-off on the look: four rendered stills (sky assembled, transit with light curve, the winding, the 492 ignition).
2. **Components:** each built in isolation, with a short motion proof.
3. **Assembly** on the narration timeline.
4. **Review rounds:** a fresh critic (a separate agent that sees only the render and the brief) on each cut. Also frozen-frame, loudness and caption-collision checks.
5. **Optional sound design:** soft transition whooshes, kept below the music.
