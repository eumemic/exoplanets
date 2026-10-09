"""FFI pixel cutouts cut with astrocut from the TESS cubes on the STScI open-data bucket (what
TESScut runs). TESScut serves ~0.2 MB/s; inside AWS a 200-s-cadence sector takes ~5 s.
"""
import glob
import os

CUBES = "s3://stpubdata/tess/public/mast/tess-s{:04d}-{}-{}-cube.fits"


def _add_column_wcs(self, table_header, wcs_dict):
    """astrocut 1.4.0's CubeCutout._add_column_wcs never matches a TDIM keyword (its test also
    requires kwd[:-1] == "TTYPE"), so its cutouts lack the column WCS keywords that TESScut files
    carry and transit-diffImage and TRICERATOPS read (1CRPX4, 1CRV4P, ...). Same insertion,
    condition fixed."""
    for kwd in [k for k in table_header if k.startswith("TDIM")]:
        for wcs_key, (val, com) in wcs_dict.items():
            table_header.insert(kwd, (wcs_key.format(int(kwd[4:]) - 1), val, com))


def cut(tic, ra, dec, size, out, sectors=None):
    """Cut size x size pixels around (ra, dec) from the cube of every sector that observed the star
    (or only `sectors`) into out/, skipping sectors already cut there. Returns the cutout paths."""
    import astrocut
    from astrocut import cube_cutout
    from astropy.coordinates import SkyCoord
    from tess_stars2px import tess_stars2px_function_entry

    cube_cutout.CubeCutout._add_column_wcs = _add_column_wcs
    os.makedirs(out, exist_ok=True)
    r = tess_stars2px_function_entry(int(tic), float(ra), float(dec))
    for sec, cam, ccd in zip(r[3], r[4], r[5]):
        if sectors is not None and int(sec) not in sectors:
            continue
        if not glob.glob(os.path.join(out, f"tess-s{int(sec):04d}-*.fits")):
            try:
                astrocut.cube_cut(CUBES.format(int(sec), int(cam), int(ccd)),
                                  SkyCoord(float(ra), float(dec), unit="deg"), size, output_path=out,
                                  verbose=False)
            except FileNotFoundError:      # no cube on the bucket for this sector
                pass
    return sorted(glob.glob(os.path.join(out, "*.fits")))
