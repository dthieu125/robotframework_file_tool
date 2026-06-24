# Robot Framework analysis & helper toolkit

A small toolkit with a **Flask** web UI and a **command-line** utility for **Robot Framework**: inspect `.robot` / `.resource` files, run tests, merge several `output.xml` files into one report, and format test case names.

*Vietnamese documentation: [README.vi.md](README.vi.md)*

## Requirements

- Python **3.9+** recommended (`start.bat` / `start.sh` assume Python is on `PATH`)
- Packages listed in [`requirements.txt`](requirements.txt): `flask`, `robotframework`, `werkzeug`

## Quick setup

```bash
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
mkdir -p uploads results   # on Windows, create empty `uploads` and `results` folders if needed
```

## Running the web app

- **Windows:** run [`start.bat`](start.bat) — creates `venv` if missing, installs dependencies, opens the browser at `http://localhost:5000`, then runs `python app.py`.
- **Linux/macOS:** run [`start.sh`](start.sh) the same way (uses `python3`).

Or manually (with the virtual environment activated):

```bash
python app.py
```

- By default the server listens on **all interfaces** (`0.0.0.0`), port **`5000`**.
- Change the port with the `PORT` environment variable, e.g. `set PORT=8080` (Windows) or `PORT=8080 python app.py`.

Upload limit: **200 MB** (configured in `app.py`).

Uploads and generated artifacts are stored under **`uploads/`** and **`results/`** (consider adding these directories to `.gitignore`).

## Web features

| Feature | Description |
|--------|-------------|
| **File statistics** | Parse Robot file content: test cases, keywords, settings, variables, summary (`/api/statistics`). |
| **Run Robot** | Upload a `.robot` file, optional config, include/exclude tags, variables; stream console output via SSE; download a zip of results (`/api/run`, `/api/run/<id>/stream`). |
| **Merge reports** | Upload **at least two** `output.xml` files; identical duplicates are skipped; merges metadata and timing; optional **flatten**; produces `*_output.xml`, `*_log.html`, `*_report.html` and a zip (`/api/merge`). |
| **Test name formatter** | Preview and apply renaming rules (regex, prefix/suffix, template, numbering, …) via `/api/format/preview` and `/api/format/apply`. |

Implementation entry points: [`app.py`](app.py), merge logic [`modules/merger.py`](modules/merger.py), analysis [`modules/statistics.py`](modules/statistics.py), formatter [`modules/formatter.py`](modules/formatter.py).

## CLI: merge `output.xml` (`rf_merge.py`)

Standalone tool — no Flask required. Merges multiple Robot output XML files and optionally generates HTML log/report using `robot.rebot`.

```bash
python rf_merge.py run1/output.xml run2/output.xml
python rf_merge.py -o reports -n sprint42 *.xml
python rf_merge.py --flatten *.xml
python rf_merge.py --xml-only *.xml
```

Useful flags:

- `-o` / `--output-dir` — output directory (default: `./merged_results/`)
- `-n` / `--name` — merged suite name and file prefix (default: `merged`)
- `--flatten` — flatten all test cases to a single suite level
- `--xml-only` — only write merged XML; skip HTML generation
- `--no-dedup` — disable skipping of byte-identical duplicate files

Requires: `pip install robotframework`.

## Tests

The project includes [`tests/test_statistics.py`](tests/test_statistics.py). Run (install `pytest` if needed):

```bash
pytest tests/ -q
```

## Directory layout (short)

```
app.py              # Flask app and API
rf_merge.py         # CLI to merge output.xml
modules/            # merger, statistics, formatter
templates/          # index.html
static/             # CSS and JS
start.bat / start.sh
requirements.txt
uploads/            # temporary uploads (created by the server)
results/            # run / merge / format outputs (created by the server)
```

## Security & deployment notes

- `SECRET_KEY` is random on each start — fine for local/internal use; for production, set a stable secret via environment variables and use HTTPS / authentication if exposed.
- The server runs with **`debug=False`** by default; enable debug only for local development.

## License

Not specified in this repository — add a license file if you plan to distribute the project publicly.
