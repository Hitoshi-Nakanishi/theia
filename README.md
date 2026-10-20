# Theia

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![PySide6](https://img.shields.io/badge/GUI-PySide6-41cd52)

Theia is a fast local desktop viewer for generated Excel valuation models. Open
one workbook or a folder of company models, inspect assumptions and valuation
sheets, and compare the same metrics across companies without launching Excel.
Files and folders can also be opened from zip archives.

![Theia test screen](docs/assets/theia-screenshot.png)

Everything runs locally against files on your own disk. Nothing is uploaded.
Optional display metadata preserves spreadsheet formatting and speeds up loading.

## Quick Start

Install [Task](https://taskfile.dev/) and Python 3.11+.

```sh
cp .env.example .env       # Windows: copy .env.example .env
# set THEIA_MODELS_PATH to the folder containing your valuation workbooks

task install               # create .venv/ and install theia (editable)
task run                   # open the configured model folder
```

You can also open anything directly:

```sh
task run-path -- /path/to/a/workbook.xlsx
task run-path -- /path/to/a/folder
task run-path -- /path/to/models.zip
```

The viewer accepts drag-and-drop of files, zips, or folders.

## Features

- Browse company models by collection and folder, using your own directory labels.
- Open a single Excel file, a folder, or a zip by menu, CLI argument, or drag-and-drop.
- Open multiple Excel files together; folder and zip browsing accepts arbitrary filenames.
- Compare selected cells across the files in the current companies filter, with numeric sorting and CSV export.
- Use the neutral Theia theme or Midnight, Aurora, and Ember, with light and dark modes.
- Toggle the navigation sidebar when the table needs the full window width.
- Load pre-formatted `.arrow` sidecars when present for near-instant sheet display.
- Render Excel-style number formats from sidecar metadata when available.
- Preserve hidden rows/columns, merged cells, freeze panes, and outline groups.
- Switch sheets with bottom tabs, inspect a selected cell, or jump directly to an address.
- Keep one workbook and one decoded sheet open, with at most four recently rendered sheet models.
- Load data on demand; metadata and column-width caches are bounded.
- Optionally compile a small Cython extension, with a pure-Python fallback.

## Demo Workbook

The repository includes an anonymized workbook for smoke tests and README
screenshots:

```sh
task run-path -- examples/demo_models/0000.T_Demo_Model.xlsx
```

The workbook and sidecar use fictional labels only. They do not contain source identifiers, client identifiers, or real holdings.

## Compare Workbooks

1. Open a folder, zip, or multiple Excel files with `Ctrl+O` or drag-and-drop.
2. Open a representative workbook and sheet. Select the cells to compare;
   use Ctrl-click for separate cells, up to 64 cells per comparison.
3. Optionally filter the companies list to limit the comparison to matching files.
4. Choose **Compare > Compare Selected Cells** (`Ctrl+Shift+C`). Each file
   becomes a row, and each selected cell becomes a comparison column.
5. Click column headers to sort, filter the results, or export the visible rows
   in their current order to a UTF-8 CSV. Double-click a result to open its source cell.

Extraction runs in a background thread, opening one workbook at a time and
retaining only the extracted values. It reads the selected sheet from each
workbook; it does not keep all source sheets or create a widget per company.
Cancel keeps the results already read. Extract / refresh reads the files again.

Comparison uses the same sheet name and cell addresses in each file. By default,
it checks text labels and units to the left and the nearest text header above each selected
cell against the representative workbook. A mismatch leaves that result blank
and records the reason in Status. This is a local label check, not a complete
schema or unit check. Cells without text anchors use addresses only. The checkbox
can disable label checks when address-only extraction is intentional.

Missing sheets, unreadable files, blank cells, and missing cached values are
reported in Status instead of being treated as zero. CSV preserves raw numeric
values, source paths, sheet names, and cell addresses. Values use the workbook's
units; percentages may export as ratios. Text that could execute as a spreadsheet
formula is prefixed with an apostrophe in CSV.

Formulas are **not recalculated**. Workbooks must already contain saved calculation
results. Layout changes, differing units, and differing periods need to be
resolved before treating the extracted values as comparable.

For workbooks with different amounts of history, enable **Locate cells by item
labels and header occurrence**, then click **Extract / refresh**. The viewer finds
the row by its item label, finds the header row by its label when available, and
uses the same occurrence of the selected column header. For example, the first
`Forecast` column remains the first `Forecast` column even if more actual years
precede it. Units are checked, and missing or ambiguous labels leave a blank
result with a reason. If the header row has no label, its row number stays fixed.

This compares the same relative column category, which can represent different
calendar periods in different workbooks. Inspect **Extracted cells / headers**
for each file's actual header and cell address; those details also appear in CSV
and cell tooltips. Double-click opens the cell actually extracted.

Use **Save comparison preset** to store the sheet, items and matching rules in
a local JSON file. On a later folder, choose **Compare > Load Comparison Preset**
to repeat the extraction without selecting cells again. Presets contain labels
and selectors, not workbook paths or extracted numbers. Keep private presets
outside the public checkout. Matching a folder/group label in the companies
filter includes its child files, so date-named folders can select an event month.

## Native Rendering And Performance

Theia uses native Qt widgets (C++) and the Rust-backed Calamine Excel parser.
Python coordinates the interface and reads only requested sheets. No browser engine
is embedded. Arrow is imported only when a display sidecar is actually opened.

A local Windows run on 2026-10-21 used 24 fictional workbooks, each with three
1,501-row × 16-column sheets. Each company timing includes displaying all three
sheets and processing UI events. Resident memory is the process working set.

| Measure | Previous layout | Current layout |
|---|---:|---:|
| Idle memory | 69.7 MiB | 59.6 MiB |
| Memory after visiting every model | 94.0 MiB | 69.2 MiB |
| Three-sheet company visit, median | 233.2 ms | 195.7 ms |
| Three-sheet company visit, p95 | 258.3 ms | 223.8 ms |

These are local measurements with synthetic data, not latency or memory guarantees.
Repeat the same check with the viewer's virtual environment:

```sh
python tools/benchmark_viewer.py --prepare --fixture build/benchmark-models
python tools/benchmark_viewer.py --fixture build/benchmark-models --output build/result.json
```

The test workflow covers Windows and macOS. This measurement was taken on Windows;
macOS runtime and packaging still need verification on a Mac.

## Model Folders

`task run` opens `THEIA_MODELS_PATH`, read from the environment or `.env`. When
unset, Theia uses `~/Documents/Theia/models`. A `DATA_PATH` override places the
default folder at `$DATA_PATH/models`.

```text
models/
|-- Company_A.xlsx
`-- sector/
    `-- Company_B.xlsx
```

There is no required source or filename convention. Workbooks can be `.xlsx`,
`.xls`, `.xlsm`, or `.xlsb`. Optional `.json` and `.arrow` display metadata can sit
beside a workbook. Use `task run-path -- <path>` to open any file, folder, or zip.

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+O` | Open file or zip |
| `Ctrl+Shift+O` | Open folder |
| `Ctrl+B` | Toggle sidebar |
| `Ctrl+L` | Focus the companies filter |
| `Ctrl+Shift+L` | Focus the sheets filter |
| `Ctrl+Shift+F` | Freeze panes at the current cell |
| `Ctrl+Shift+U` | Unfreeze panes |
| `Ctrl+Shift+G` | Toggle outline groups |
| `Ctrl+Shift+C` | Compare selected cells across the current companies filter |
| `Ctrl+Arrow` | Jump to the next non-empty cell |
| `Ctrl+Shift+Arrow` | Extend the selection to the next non-empty cell |

## `task` Commands

| Command | What it does |
|---|---|
| `task` | List available tasks |
| `task install` | Create `.venv/` and install `theia` editable |
| `task paths` | Print the configured model folder |
| `task run` | Launch the viewer on the configured model folder |
| `task run-path -- <path>` | Launch the viewer on an explicit file, folder, or zip |
| `task build-cython` | Compile the optional native accelerator |
| `task clean` | Remove `.venv/` and build artifacts |

## Optional Native Accelerator

The flat-list construction and per-cell display lookup are also available as a
small Cython extension (`theia/_arrow_fast.pyx`). It is optional:
`arrow_model.py` falls back to identical pure-Python code when the compiled
module is absent.

```sh
task build-cython
```

## Project Layout

```text
theia/
|-- app.py          # MainWindow, open file/folder/zip, collection -> folder -> company tree
|-- compare.py      # background cell extraction, comparison table, CSV export
|-- table.py        # FrozenPaneTable, keyboard navigation, fast delegate
|-- model.py        # SheetModel and Excel number-format parser
|-- arrow_model.py  # ArrowSheetModel backed by a memory-mapped Arrow RecordBatch
|-- theme.py        # Theme palettes and Qt stylesheet generation
|-- _arrow_fast.pyx # optional Cython hot path
|-- workbook.py     # lazy CalamineWorkbook wrapper
`-- paths.py        # DATA_PATH and archive path resolution
```

## Verification

```sh
.venv/Scripts/python.exe -m unittest discover -s tests -v
# macOS/Linux: .venv/bin/python -m unittest discover -s tests -v
```

Tests generate fictional workbooks in temporary directories, including a
120-file comparison, missing formula caches, label/period mismatches, corrupt
files, zip entries, sorting/export, cancellation, and viewer navigation.

## Privacy

Theia is designed so a public checkout carries no proprietary information:

- It reads only local files and uploads nothing.
- Collection and folder labels come from local directory names.
- `.env` and build artifacts are gitignored.

## Name

Theia does one thing: it lets you view models quickly without launching
Excel.
