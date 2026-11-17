# YBlade v3 - import wind turbine blades into Fusion 360

A Fusion 360 script that turns a wind turbine blade design into one solid body.
It reads a [QBlade](https://www.q-blade.org/) blade file with its airfoil, or a
single combined `.json` file, and lofts a smooth blade through every station.

![Blade Import Demo](Blade%20importing.gif)

## What's new in v3

v3 is mostly fixes. If v2 gave you a bumpy leading edge, a failed loft or a
blade with the wrong thickness, this is why:

- **Real loft instead of a sweep.** v2 swept the first section along a guide
  rail, which only approximates the chord and twist between stations and left
  a wavy leading edge. v3 draws every station and lofts through all of them.
- **Sharp trailing edges work.** QBlade airfoil files start and end on the same
  point, so the line that closes the outline has zero length, and a loft
  through such outlines fails (`ASM_BAD_UV_SKIN_DIR` and similar). v3 opens the trailing edge to a
  minimum thickness you choose (0.5 mm by default), which is also what a
  3D printer can actually make.
- **Stations are no longer thrown away.** v2 skipped a station if its chord
  changed less than 1 cm and its twist less than 1°, which on a small blade
  removed most of them. v3 leaves a station out only if the blade would move
  less than a set tolerance (0.05 mm by default) without it.
- **Section shape can change along the blade.** In the combined `.json` format
  every station may carry its own outline, e.g. thick at the root and thin at
  the tip.
- **Your own sketches stay visible.** v2 hid every sketch in the component.
- **Running it twice is safe.** v2 never ended, so running it again in the same
  Fusion session could attach its handlers twice and reuse a stale airfoil file.
- **A clearer dialog.** File names instead of long paths, short labels with
  explanations in the tooltips, and a preview of what will be built - number
  of stations, blade length, skipped circular root sections - before you press
  Import.
- **Repeated points, reversed outlines and Lednicer-format airfoil files** are
  handled.
- **No toolbar button.** A script ends when its dialog closes, so a button it
  leaves behind stops working. Run YBlade from Scripts and Add-Ins.

The way sections are placed is unchanged from v2: a QBlade blade that imported
fine before comes out in the same place, to within a fraction of a millimetre.

## Installation

1. Download this repository (Code -> Download ZIP) and unzip it, or clone it.
2. In Fusion 360: **Utilities -> Add-Ins -> Scripts and Add-Ins**.
3. Next to "My Scripts" press **+** and choose the downloaded folder.
4. **YBlade** appears in the list.

You can also copy the folder into Fusion's script folder:

- **Windows:** `%appdata%\Autodesk\Autodesk Fusion 360\API\Scripts`
- **macOS:** `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/Scripts`

v3 uses its own command name, so it can sit next to an older YBlade.

## Usage

1. Open or create a design.
2. Run **YBlade** from Scripts and Add-Ins.
3. **Choose blade file...** - a QBlade `.bld`, or a `.json` from
   QBlade esay / Vindmølle Designer.
4. For a `.bld` only: **Choose airfoil file...** - the `.afl` the blade uses
   (QBlade: Airfoil Design -> select the airfoil -> Export).
5. Check *What will be built*, then press **Import**.

The dialog shows the name and folder of each chosen file. Hover over a
setting for an explanation.

### Settings

| Setting | What it does |
|---|---|
| Trailing edge | The trailing edge is opened to at least this thickness. A sharp edge cannot be lofted or printed; 0.5 mm suits a 0.4 mm nozzle. |
| Tolerance | A station is left out when the blade would move less than this without it. 0 keeps every station. |
| Units | *Auto* reads metres from QBlade files and the `units` field from `.json` files. Choose a unit only if your file uses something else. |
| Root at Z = 0 | Moves the blade so its root is at Z = 0. Untick it to keep the blade at its real distance from the rotor centre. |
| Centre mass on Z | Moves the finished blade so its centre of mass is on the Z axis and the root at Z = 0. |
| Edge sketches | Draws the leading edge (solid) and the trailing edge (dashed) as splines, handy for modelling a tip or a root fitting. |

### Result and orientation

You get one solid body, named after the file, plus one sketch and construction
plane per station (hidden) - all in one timeline group.

- The blade runs along **+Z**, root to tip.
- The sections lie in XY planes, stacked on the pitch axis.
- The rotor axis is parallel to **Y**; the wind comes from the **-Y** side.
  The flatter (pressure) side of the blade faces the wind.

To build a rotor, untick *Root at Z = 0* so the blade keeps its real
radius, then make a circular pattern of the body around the Y axis (3 copies
for a 3-bladed rotor). Never mirror a blade - that turns the airfoil upside
down.

## The combined .json format

One file holds the stations and the section outline. Fysik Klubben's
Vindmølle Designer exports it, and it is easy to write from a spreadsheet or a
script.

```json
{
  "meta":    { "name": "My blade", "units": "Meter" },
  "airfoil": { "name": "NACA 4812", "coordinates": [[1.0, 0.0], [0.98, 0.01], "..."] },
  "blade": [
    { "pos": 0.0916, "chord": 0.0733, "twist": 19.15, "p_axis": 0.296 },
    { "pos": 0.1074, "chord": 0.0678, "twist": 16.26, "p_axis": 0.296 },
    { "pos": 0.36,   "chord": 0.0257, "twist": 1.24,  "p_axis": 0.296,
      "points": [[1.0, 0.0], "..."] }
  ]
}
```

| Field | Meaning |
|---|---|
| `meta.units` | `Meter`, `Decimeter`, `Centimeter` or `Millimeter` (default `Meter`). Applies to `pos` and `chord`. |
| `airfoil.coordinates` | The section outline for chord 1, Selig order: trailing edge -> top -> nose -> bottom -> trailing edge. |
| `blade[].pos` | Distance from the rotor centre. |
| `blade[].chord` | Chord length. |
| `blade[].twist` | Twist in degrees. |
| `blade[].p_axis` | Pitch axis as a fraction of the chord from the nose (default 0.25). |
| `blade[].points` | Optional: this station's own outline, same format as `airfoil.coordinates`. Use the same number of points at every station so the loft can match them up. |

`airfoil` may be left out if every station has `points`. `offset_x` and
`offset_y` are read but ignored - see Known limitations.

An example is in `bladeExample/Combined json/`.

## Troubleshooting

**"Fusion could not loft through the stations".** Try a larger *Trailing
edge* (e.g. 0.8 mm) or a larger *Tolerance*. Very thin, very
twisted sections near the tip are the usual cause.

**"gave 0 closed regions" / "fewer than five distinct points".** The airfoil
file is not a single outline. Open it in a text editor: it should be one list of
x y pairs, or Lednicer format with the point counts on the second line.

**The blade starts later than in QBlade.** Circular root sections are left out
on purpose - model the root fitting yourself. The status box says how many were
skipped.

**The blade looks thicker or thinner than expected.** In QBlade files every
station uses the airfoil file you chose. If your blade uses several airfoils,
use the combined `.json` format with `points` per station.

## Known limitations

- **One airfoil for QBlade files.** QBlade blade files name polar files, not
  airfoil files, so YBlade cannot look the airfoils up. Every station gets the
  shape from the `.afl` you choose.
- **Offsets are ignored.** QBlade's OFFSET_X / OFFSET_Y (sweep and prebend) are
  not applied; every section is stacked on its pitch axis. The status box warns
  when a file has offsets.
- **Circular root sections are skipped**, see above.

## For developers

The file reading and the geometry do not use the Fusion API and are tested
without Fusion, against a small stand-in for the API in `tests/fake_adsk`:

```bash
python3 -m unittest discover -s tests -v
```

The tests also check that v3 places the sections where v2 did, and that no
left-out station lies further than the tolerance from the blade.

## Changelog

- **3.0.0 (2026-11)** - Loft through all stations instead of a guided sweep;
  trailing edge opened to a minimum thickness; tolerance-based station thinning;
  per-station outlines in the `.json` format; preview in the dialog; only the
  script's own sketches are hidden; the script ends cleanly; works in direct
  modelling designs; tests.
- **2.x (2025-12)** - Solid-only workflow, status log, toolbar button,
  hub-offset removal, centre-of-mass positioning, QBlade CE 2.x files.
- **1.x (2019-2021)** - Original script by Jan Mrázek.

## Credits

Original script by Jan Mrázek ([yaqwsx](https://github.com/yaqwsx)), 2019-2021.
QBlade CE 2.x support, v2 and v3 by sophusand and
[Fysik Klubben](https://www.instagram.com/fysik_klubben/).

MIT licence - see `LICENSE`.
