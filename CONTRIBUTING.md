# Contributing

Report the expected result, actual result, reproduction steps, OS and Python version. Use fictional workbooks and remove private
data from screenshots and attachments. See [Security](SECURITY.md) for confidential reports.

## Development

Use Python 3.11+ and a virtual environment. From the checkout:

```sh
python -m pip install -e ".[arrow]"
python -m unittest discover -s tests -v
```

Keep changes small and cover changed behavior. Tests generate temporary fictional workbooks for navigation, comparison, formula
caches, labels, zip handling, CSV export and cancellation. They require no private data or services.

The [CI workflow](.github/workflows/native-tests.yml) tests Windows and macOS, builds the package and opens the installed
viewer. It also checks a minimal install without Arrow. Source is under `theia/`: `app.py` owns the window, `compare.py`
extraction, `workbook.py` lazy reads, and `model.py` and `arrow_model.py` sheet display.

## Optional acceleration

Qt widgets and the Calamine parser handle rendering and Excel reads. Theia loads sheets on demand, keeps one workbook and one
decoded sheet, and caches at most four rendered sheet models. Arrow support is optional and imported only for sidecars.

`task build-cython` compiles `theia/_arrow_fast.pyx` for Arrow cell lookup. The viewer uses the same pure-Python implementation
when the extension is absent. See the Taskfile for platform compiler requirements.

### Reproduce the performance check

```sh
python tools/benchmark_viewer.py --prepare --fixture build/benchmark-models
python tools/benchmark_viewer.py --fixture build/benchmark-models --output build/result.json
```

The October 21, 2026 Windows measurement used 24 fictional workbooks, each with three 1,501-row by 16-column sheets. A company
visit displayed all three sheets and processed UI events. Memory is the process working set.

| Measure | Previous layout | Measured layout |
| --- | ---: | ---: |
| Idle memory | 69.7 MiB | 59.6 MiB |
| Memory after visiting every model | 94.0 MiB | 69.2 MiB |
| Three-sheet company visit, median | 233.2 ms | 195.7 ms |
| Three-sheet company visit, p95 | 258.3 ms | 223.8 ms |

These synthetic results are a reference for repeating the check, not performance guarantees or macOS measurements.

## Publication and license

The maintainer runs [publication checks](PUBLICATION.md); contributors do not need the private policy. Keep configured Git hooks
enabled and private workbooks, metadata, `.env` files and build artifacts out of commits.

Contributions use the [MIT License](LICENSE). Review [third-party notices](THIRD_PARTY_NOTICES.md) before distributing Qt or
other dependencies with an application. The current build produces a Python wheel.
