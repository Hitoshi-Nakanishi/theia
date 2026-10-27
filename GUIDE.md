# Theia user guide

[Quick start](README.md#quick-start) · [Demo workbook](examples/demo_models/0000.T_Demo_Model.xlsx)

## Files and folders

Open a workbook, a folder, a zip archive or several files together. Filenames and folder names are your own labels; no naming
convention is required. Use the File menu, drag-and-drop, or pass a path:

```sh
python -m theia examples/demo_models/0000.T_Demo_Model.xlsx
task run -- /path/to/models.zip
```

Relative paths are read from the directory where you run the command. `task run` without a path opens `THEIA_MODELS_PATH`, read
from the environment or `.env`. Copy `.env.example` to `.env` to set it once. Otherwise the default is
`~/Documents/Theia/models`, or `$DATA_PATH/models` when `DATA_PATH` is set. Use `task paths` to see the chosen folder.

If that folder does not exist, the window shows the path and offers **Open workbook** and **Open folder**.

### Optional display metadata

Theia reads Excel number formats directly. A workbook may also have `.json` display metadata or a pre-formatted `.arrow` sidecar
for faster sheet loading. Ordinary workbooks need neither. To enable Arrow support, install from the checkout with:

```sh
python -m pip install ".[arrow]"
```

## Comparing models

Open a collection, choose a representative workbook and sheet, then select up to 64 cells. Ctrl-click selects separate cells.
Filter the companies list if needed, then choose **Compare > Compare Selected Cells** (`Ctrl+Shift+C`). A matching group or
folder label includes its child files.

Extraction opens one workbook at a time in the background. Cancel keeps the results already read; **Extract / refresh** reads
the files again. Sort by clicking a column header. CSV export preserves the visible rows and their order; double-clicking a
result opens the source cell.

### Match by address

The default uses the same sheet name and cell addresses in each workbook. It also compares nearby text labels and units, and the
nearest header above the selected cell, with the representative workbook. Mismatches leave a blank result with a reason in
**Status**. Cells without text anchors use addresses only. Disable the label-check checkbox only when address-only extraction is
intentional.

### Match by labels

For models with different amounts of history, enable **Locate cells by item labels and header occurrence**, then click **Extract
/ refresh**. Theia finds the item row, the labelled header row where available, and the same occurrence of the selected column
header. The first `Forecast` column stays the first `Forecast` column even when more actual years precede it. If the header row
has no label, its row number stays fixed.

Missing or ambiguous labels and unit mismatches leave a blank result with a reason. **Extracted cells / headers**, tooltips and
CSV show the actual address and header for each workbook. Double-click opens that extracted cell.

### Results and presets

Theia does not recalculate formulas. Workbooks need saved calculation results. Missing sheets, corrupt files, empty cells and
missing formula caches appear in **Status**, not as zero. Label checks are local checks, not a complete schema validation. A
matching column category can still represent different calendar periods: review units, periods and layout before comparison.

CSV keeps raw numeric values, workbook units, source paths, sheet names and cell addresses. Percentages may export as ratios.
Text that could execute as a spreadsheet formula is prefixed with an apostrophe.

Use **Save comparison preset** to save the sheet, items and matching rules in a local JSON file. **Compare > Load Comparison
Preset** repeats the extraction on another collection. Presets contain labels and selectors, not workbook paths or extracted
values; keep private presets outside the public checkout.

## Display and navigation

Switch sheets with the tabs above the table, inspect the selected cell in the address bar, or jump to an address directly.
Column widths follow formatted values. Long titles can extend into adjacent empty cells; **View > Fit column widths** restores
automatic widths after resizing.

The bottom-right controls zoom the whole interface from 50% to 200%, including menus, sheet tabs and cells. Click the percentage
to return to 100%. The chosen zoom is remembered. **View > Theme** offers Theia, Midnight, Aurora and Ember in light and dark.

| Shortcut | Action |
| --- | --- |
| `Ctrl/Cmd+mouse wheel` | Zoom the interface |
| `Ctrl/Cmd++` / `Ctrl/Cmd+-` | Zoom in / out |
| `Ctrl/Cmd+0` | Reset zoom |
| `Arrow` / `Shift+Arrow` | Move or extend the selection, including across frozen panes |
| `Enter` / `Shift+Enter` | Move down / up |
| `Tab` / `Shift+Tab` | Move right / left |
| `Ctrl+O` / `Ctrl+Shift+O` | Open files or a zip / open a folder |
| `Ctrl+B` | Toggle the sidebar |
| `Ctrl+L` / `Ctrl+Shift+L` | Focus the companies / sheets filter |
| `Ctrl+Shift+F` / `Ctrl+Shift+U` | Freeze at the current cell / unfreeze |
| `Ctrl+Shift+G` | Toggle outline groups |
| `Ctrl+Shift+C` | Compare selected cells |
| `Ctrl+Arrow` / `Ctrl+Shift+Arrow` | Jump to the next non-empty cell / extend selection to it |

## Task commands

| Command | Action |
| --- | --- |
| `task` | List tasks |
| `task install` | Create `.venv` and install Theia; `task run` does this when needed |
| `task run` | Open the configured model folder |
| `task run -- <path>` | Open a workbook, folder or zip; `run-path` is an alias |
| `task paths` | Print the model folder |
| `task build-cython` | Build the optional accelerator |
| `task clean` | Remove the environment and build artifacts |
