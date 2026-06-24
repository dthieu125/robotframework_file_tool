# Robot Framework File Tool

A small Flask web app plus a standalone CLI utility for Robot Framework workflows: analyze `.robot` / `.resource` files, run tests, merge multiple `output.xml` files, and format test case names.

## Requirements

- Python 3.9+ recommended
- Dependencies from [`requirements.txt`](requirements.txt): `flask`, `robotframework`, `werkzeug`

## Quick Setup

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Linux/macOS
source venv/bin/activate

pip install -r requirements.txt
```

## Running The Web App

On Windows:

```bash
start.bat
```

On Linux/macOS:

```bash
./start.sh
```

Or run manually:

```bash
python app.py
```

The app listens on `0.0.0.0:5000` by default. Change the port with `PORT`, for example:

```bash
set PORT=8080
python app.py
```

Upload limit is 200 MB. Runtime files are stored in `uploads/` and `results/`; both are ignored by git.

## Web Features

| Feature | Description |
| --- | --- |
| Report Merger | Upload at least two Robot Framework `output.xml` files, deduplicate identical files, merge results, and generate XML/log/report output. |
| File Statistics | Analyze Robot files and list test cases, keywords, settings, variables, line numbers, and source content. |
| Test Runner | Upload and run a `.robot` file, stream console output in real time, and download generated results. |
| Name Formatter | Preview and apply bulk test case rename rules such as regex replacement, prefix/suffix, templates, and numbering. |

## Report Merger Notes

The web Report Merger supports two merge modes:

- Combine: include tests from all input files.
- Update / Replace: later files replace same-named tests from earlier files, using Robot Framework `rebot --merge`.

Report Merger settings include:

- Keep old result history beside the latest result, or keep only the latest status.
- Clear selected input files after a successful merge.
- Automatically delete old upload/result files after a configured number of hours.
- Manually clean old upload/result files from the settings dialog.

If Output name is left empty, the generated files are:

- `output.xml`
- `log.html`
- `report.html`

If Output name is set, it is used as a prefix:

- `<name>_output.xml`
- `<name>_log.html`
- `<name>_report.html`

## CLI: `rf_merge.py`

`rf_merge.py` is a standalone merge tool and does not require Flask.

```bash
python rf_merge.py run1/output.xml run2/output.xml
python rf_merge.py -o reports -n sprint42 run1/output.xml run2/output.xml
python rf_merge.py --flatten *.xml
python rf_merge.py --xml-only *.xml
python rf_merge.py --update old_results.xml new_rerun.xml
python rf_merge.py --update --latest-only old_results.xml new_rerun.xml
```

Useful flags:

- `-o` / `--output-dir`: output directory, default `./merged_results/`.
- `-n` / `--name`: file prefix. Leave empty/default to create `output.xml`, `log.html`, and `report.html`.
- `--suite-name`: override the top-level suite name.
- `--flatten`: flatten all test cases to one suite level.
- `--xml-only`: only create merged XML and skip HTML generation.
- `--update`: replace same-named tests from earlier files with later files.
- `--latest-only`: with `--update`, remove Robot Framework old-result history and keep only the latest status.
- `--no-dedup`: disable deduplication of byte-identical files.

## API Entry Points

| Endpoint | Purpose |
| --- | --- |
| `POST /api/merge` | Merge uploaded `output.xml` files. |
| `GET /api/merge/<run_id>/report` | View merged `report.html`. |
| `GET /api/merge/<run_id>/log` | View merged `log.html`. |
| `GET /api/download/<run_id>` | Download generated ZIP results. |
| `GET/POST /api/settings` | Read or update app settings such as cleanup age. |
| `POST /api/cleanup` | Clean old upload/result files immediately. |
| `POST /api/statistics` | Analyze Robot file content. |
| `POST /api/run` | Start a Robot test run. |
| `GET /api/run/<run_id>/stream` | Stream Robot run output via SSE. |
| `POST /api/format/preview` | Preview test name formatting changes. |
| `POST /api/format/apply` | Apply formatting and download the modified file. |

## Tests

The project includes [`tests/test_statistics.py`](tests/test_statistics.py). Install `pytest` if needed:

```bash
pip install pytest
pytest tests/ -q
```

## Directory Layout

```text
app.py              # Flask app and HTTP API
rf_merge.py         # Standalone CLI report merger
modules/            # merger, statistics, formatter logic
templates/          # Web UI
static/             # CSS and JavaScript
refs/               # Reference code
tests/              # Tests
start.bat / start.sh
requirements.txt
uploads/            # Runtime uploads, ignored by git
results/            # Runtime outputs, ignored by git
technical_docs/     # Local technical notes, ignored by git
```

## Security And Deployment Notes

- The app is designed for local or trusted internal use.
- There is no authentication layer by default.
- `SECRET_KEY` is generated randomly at startup.
- Flask runs with `debug=False` by default.
- Use HTTPS and authentication if exposing the app outside a trusted network.
