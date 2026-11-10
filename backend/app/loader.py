"""Normalize files (encoding, line endings, Excel sheets) and load them into DuckDB.

Every source table is stored as all-VARCHAR plus a hidden row id. Types are inferred later
by the profiler, so messy cells ("NA" in a number column, "$1,200") survive loading and can
be shown to the user instead of silently becoming NULL.
"""

from __future__ import annotations

import csv
import re
import tempfile
from datetime import date, datetime, time
from pathlib import Path

import openpyxl

from . import store
from .sql import ROW_ID, ident, lit

_TMP = Path(tempfile.mkdtemp(prefix="dataful-"))


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "data"


def decode_bytes(raw: bytes) -> str:
    """Decode text, trying UTF-8 (with/without BOM) before legacy Windows/Latin encodings."""
    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_text(text: str) -> str:
    """Unify line endings: Windows CRLF and old-Mac CR-only files both become LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _table_name(dataset_id: str) -> str:
    return "src_" + dataset_id.replace("-", "_")


def _create_table(table: str, csv_path: Path, delim: str | None = None) -> None:
    opts = "all_varchar=true, header=true, null_padding=true"
    if delim:
        opts += f", delim={lit(delim)}, quote='\"'"
    store.execute(f"DROP TABLE IF EXISTS {ident(table)}")
    store.execute(
        f"CREATE TABLE {ident(table)} AS "
        f"SELECT row_number() OVER () AS {ROW_ID}, * FROM read_csv({lit(str(csv_path))}, {opts})"
    )


def _register(dataset_id: str, name: str, file: str, sheet: str | None, table: str, demo: bool) -> store.DatasetState:
    rows = store.query(f"SELECT count(*) FROM {ident(table)}")[0][0]
    columns = [c for c in store.table_columns(table) if c != ROW_ID]
    ds = store.DatasetState(id=dataset_id, name=name, file=file, sheet=sheet, table=table,
                            rows=rows, columns=columns, demo=demo)
    store.register(ds)
    return ds


def load_csv(raw: bytes, file: str, name: str | None = None, dataset_id: str | None = None,
             demo: bool = False) -> store.DatasetState:
    """Normalize a CSV/TSV and register it as one dataset."""
    text = normalize_text(decode_bytes(raw))
    dataset_id = store.unique_id(dataset_id or slugify(Path(file).stem))
    path = _TMP / f"{dataset_id}.csv"
    path.write_text(text, encoding="utf-8")
    table = _table_name(dataset_id)
    delim = "\t" if file.lower().endswith(".tsv") else None
    _create_table(table, path, delim)
    return _register(dataset_id, name or Path(file).stem, file, None, table, demo)


def _cell_text(value: object) -> str | None:
    """Render an Excel cell the way a user would see it, as text."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, datetime):
        return value.date().isoformat() if value.time() == time(0) else value.isoformat(sep=" ")
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    return text if text.strip() else None


def _sheet_rows(ws) -> list[list[str | None]]:
    """All non-empty rows of a sheet, trimmed to the header's width."""
    rows: list[list[str | None]] = []
    for raw_row in ws.iter_rows(values_only=True):
        row = [_cell_text(v) for v in raw_row]
        if any(v is not None for v in row):
            rows.append(row)
    if not rows:
        return []
    header = rows[0]
    width = max((i + 1 for i, v in enumerate(header) if v is not None), default=0)
    return [(r + [None] * width)[:width] for r in rows]


def _unique_headers(header: list[str | None]) -> list[str]:
    seen: dict[str, int] = {}
    out = []
    for i, h in enumerate(header):
        name = (h or f"Column {i + 1}").strip()
        if name in seen:
            seen[name] += 1
            name = f"{name} ({seen[name]})"
        else:
            seen[name] = 1
        out.append(name)
    return out


def load_excel(path_or_bytes: Path | bytes, file: str, demo: bool = False,
               name_prefix: str | None = None) -> list[store.DatasetState]:
    """Load every non-empty sheet of a workbook as its own dataset."""
    source = path_or_bytes
    if isinstance(path_or_bytes, bytes):
        source = _TMP / f"upload-{slugify(file)}.xlsx"
        source.write_bytes(path_or_bytes)
    wb = openpyxl.load_workbook(source, read_only=True, data_only=True)
    datasets = []
    try:
        for ws in wb.worksheets:
            rows = _sheet_rows(ws)
            if len(rows) < 2:
                continue
            dataset_id = store.unique_id(f"{slugify(Path(file).stem)}-{slugify(ws.title)}")
            path = _TMP / f"{dataset_id}.csv"
            with path.open("w", newline="", encoding="utf-8") as fh:
                writer = csv.writer(fh)
                writer.writerow(_unique_headers(rows[0]))
                writer.writerows(rows[1:])
            table = _table_name(dataset_id)
            _create_table(table, path, delim=",")
            title = f"{name_prefix or Path(file).stem} · {ws.title}"
            datasets.append(_register(dataset_id, title, file, ws.title, table, demo))
    finally:
        wb.close()
    return datasets


def load_upload(raw: bytes, filename: str) -> list[store.DatasetState]:
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xlsm")):
        return load_excel(raw, filename)
    if lower.endswith((".csv", ".tsv", ".txt")):
        return [load_csv(raw, filename)]
    raise ValueError("Unsupported file type. Upload a .csv, .tsv or .xlsx file.")


DATASET_DIR = Path(__file__).resolve().parents[2] / "dataset"

DEMO_CSVS = [
    ("olympics_athletes/athlete_events.csv", "olympics-athlete-events", "Olympic athletes"),
    ("olympics_athletes/noc_regions.csv", "olympics-noc-regions", "Olympic regions (NOC)"),
    ("Messy_Employee_dataset.csv", "messy-employees", "Employees (messy)"),
    ("extensions/crm_deals.csv", "crm-deals", "CRM deals (sample)"),
    ("ml-latest-small/movies.csv", "movielens-movies", "MovieLens movies"),
    ("ml-latest-small/ratings.csv", "movielens-ratings", "MovieLens ratings"),
]
DEMO_WORKBOOKS = [("Bookshop.xlsx", "Bookshop"), ("BookshopLibraries.xlsx", "Bookshop libraries")]


def load_demos() -> None:
    """Load the bundled demo datasets; a missing file is skipped, not fatal."""
    for rel, dataset_id, name in DEMO_CSVS:
        path = DATASET_DIR / rel
        if path.exists():
            load_csv(path.read_bytes(), path.name, name=name, dataset_id=dataset_id, demo=True)
    for rel, prefix in DEMO_WORKBOOKS:
        path = DATASET_DIR / rel
        if path.exists():
            load_excel(path, path.name, demo=True, name_prefix=prefix)
