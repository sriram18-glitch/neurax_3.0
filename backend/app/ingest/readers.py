"""Format detection and readers.

Every reader returns one or more named pandas DataFrames (Table objects).
Unsupported or corrupt inputs raise IngestError with an actionable message.
Nothing here fabricates data: if a format cannot be read, it is reported.
"""

from __future__ import annotations

import hashlib
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .errors import IngestError

TABLE_EXTENSIONS = {".csv", ".txt", ".tsv", ".mat", ".xls", ".xlsx", ".xlsm"}
ARCHIVE_EXTENSIONS = {".zip"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp", ".gif"}


@dataclass
class Table:
    name: str
    frame: pd.DataFrame
    source_file: str


@dataclass
class IngestResult:
    filename: str
    size_bytes: int
    sha256: str
    container: str
    tables: list[Table] = field(default_factory=list)
    image_files: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    extracted_root: str | None = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def sniff_container(path: Path) -> str:
    with open(path, "rb") as fh:
        head = fh.read(128)
    if head[:4] == b"PK\x03\x04":
        return "zip"
    if head[:19] == b"MATLAB 5.0 MAT-file":
        return "mat"
    if head[:8] == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
        return "ole"  # legacy xls / Arena doe
    if path.suffix.lower() in {".csv", ".txt", ".tsv"}:
        return "text"
    if path.suffix.lower() in {".xlsx", ".xlsm"}:
        return "xlsx"
    if path.suffix.lower() == ".xls":
        return "ole"
    return "unknown"


def _mat_is_valid(path: Path) -> tuple[int, bytes]:
    with open(path, "rb") as fh:
        fh.seek(124)
        trailer = fh.read(4)
    if len(trailer) < 4:
        return 0, b""
    version = int.from_bytes(trailer[0:2], "little")
    endian = trailer[2:4]
    return version, endian


def _read_text(path: Path) -> list[Table]:
    for encoding in ("utf-8", "latin-1"):
        try:
            frame = pd.read_csv(path, encoding=encoding)
            if frame.shape[1] == 1 and path.suffix.lower() in {".txt", ".tsv"}:
                alt = pd.read_csv(path, sep="\t", encoding=encoding)
                if alt.shape[1] > 1:
                    frame = alt
            return [Table(name=path.stem, frame=frame, source_file=path.name)]
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            raise IngestError("EMPTY_FILE", f"'{path.name}' contains no tabular data.")
        except pd.errors.ParserError as exc:
            raise IngestError("PARSE_ERROR", f"Could not parse '{path.name}' as delimited text.", str(exc))
    raise IngestError("ENCODING_ERROR", f"Could not decode '{path.name}' as text.")


def _read_mat(path: Path) -> list[Table]:
    version, endian = _mat_is_valid(path)
    if version != 256 or endian not in (b"IM", b"MI"):
        raise IngestError(
            "MAT_CORRUPT",
            f"'{path.name}' is not a valid MAT-file v5 (version={version}, endian={endian!r}). "
            "The file is likely corrupt or incompletely downloaded.",
            "Re-download the file and retry. Use the known-good 34.8 MB copy if available.",
        )
    try:
        from scipy.io import loadmat
    except ImportError:  # pragma: no cover
        raise IngestError("MISSING_READER", "scipy is required to read MAT files and is not installed.")

    try:
        data = loadmat(str(path), squeeze_me=True, struct_as_record=False)
    except Exception as exc:
        raise IngestError("MAT_PARSE_ERROR", f"Failed to read MAT-file '{path.name}'.", str(exc))

    tables: list[Table] = []
    for name, value in data.items():
        if name.startswith("__"):
            continue
        if isinstance(value, np.ndarray) and value.dtype.names is None and value.ndim <= 2:
            if value.ndim == 0 or value.size == 0:
                continue
            frame = pd.DataFrame(value)
            if value.ndim == 1:
                frame.columns = [name]
            frame.columns = [f"{name}_{c}" if isinstance(c, int) else str(c) for c in frame.columns]
            tables.append(Table(name=name, frame=frame, source_file=path.name))
    return tables


def _read_excel(path: Path) -> list[Table]:
    suffix = path.suffix.lower()
    try:
        if suffix == ".xls":
            sheets = pd.read_excel(path, sheet_name=None, engine="xlrd")
        else:
            sheets = pd.read_excel(path, sheet_name=None)
    except ImportError as exc:
        engine = "xlrd" if suffix == ".xls" else "openpyxl"
        raise IngestError(
            "MISSING_READER",
            f"Reading '{suffix}' files requires the optional '{engine}' package, which is not installed.",
            f"Install '{engine}' deliberately before uploading {suffix} files. No data was read.",
        )
    except Exception as exc:
        raise IngestError("EXCEL_PARSE_ERROR", f"Failed to read Excel file '{path.name}'.", str(exc))
    return [
        Table(name=f"{path.stem}:{sheet}", frame=frame, source_file=path.name)
        for sheet, frame in sheets.items()
        if frame is not None and not frame.empty
    ]


def _read_zip(path: Path, depth: int = 0, extract_dir: Path | None = None) -> tuple[list[Table], list[str], list[str], list[str], str | None]:
    tables: list[Table] = []
    images: list[str] = []
    warnings: list[str] = []
    skipped: list[str] = []
    extracted_root: str | None = None
    try:
        archive = zipfile.ZipFile(path)
    except zipfile.BadZipFile as exc:
        raise IngestError("ZIP_CORRUPT", f"'{path.name}' is not a readable ZIP archive.", str(exc))

    context = tempfile.TemporaryDirectory(prefix="neurax_zip_") if extract_dir is None else None
    tmpdir = Path(context.name) if context else Path(extract_dir)
    tmpdir.mkdir(parents=True, exist_ok=True)

    with archive:
        for member in archive.namelist():
            member_path = Path(member)
            if member.endswith("/") or "__MACOSX" in member:
                continue
            ext = member_path.suffix.lower()
            if ext in IMAGE_EXTENSIONS:
                if len(images) < 500:
                    images.append(member)
                if extract_dir is not None:
                    target = tmpdir / member
                    target.parent.mkdir(parents=True, exist_ok=True)
                    try:
                        with archive.open(member) as src, open(target, "wb") as dst:
                            dst.write(src.read())
                    except Exception as exc:  # noqa: BLE001
                        warnings.append(f"Could not extract image '{member}': {exc}")
                continue
            if ext not in TABLE_EXTENSIONS:
                skipped.append(member)
                continue
            if depth >= 2:
                skipped.append(member)
                continue
            target = tmpdir / member_path.name
            try:
                with archive.open(member) as src, open(target, "wb") as dst:
                    dst.write(src.read())
            except Exception as exc:  # corrupt member
                warnings.append(f"Could not extract '{member}': {exc}")
                continue
            try:
                nested = _read_single(target, depth=depth + 1)
                for table in nested:
                    table.name = f"{member}" if len(nested) == 1 else f"{member}::{table.name}"
                    tables.append(table)
            except IngestError as exc:
                warnings.append(f"Skipped '{member}': {exc.message}")
        if extract_dir is not None and images:
            extracted_root = str(tmpdir)
    if context:
        context.cleanup()
    return tables, images, warnings, skipped, extracted_root


def _read_single(path: Path, depth: int = 0) -> list[Table]:
    container = sniff_container(path)
    if container == "text":
        return _read_text(path)
    if container == "mat":
        return _read_mat(path)
    if container in {"xlsx", "ole"}:
        suffix = path.suffix.lower()
        if suffix in {".doe"}:
            raise IngestError(
                "BINARY_MODEL_FILE",
                f"'{path.name}' is a Rockwell Arena model file (.doe), not a dataset. "
                "Upload the matching CSV/MAT dataset instead.",
            )
        return _read_excel(path)
    if container == "zip":
        tables, images, warnings, skipped = _read_zip(path, depth=depth)
        if images:
            warnings.append(f"{len(images)} image file(s) found inside the archive.")
        return tables
    raise IngestError(
        "UNSUPPORTED_FORMAT",
        f"Unsupported file type for '{path.name}'. Supported: CSV/TXT/TSV, MAT (v5/v7), XLS/XLSX, ZIP.",
    )


def ingest_path(path: Path, extract_images_to: Path | None = None) -> IngestResult:
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise IngestError("FILE_NOT_FOUND", f"File '{path}' does not exist.")
    container = sniff_container(path)
    result = IngestResult(
        filename=path.name,
        size_bytes=path.stat().st_size,
        sha256=_sha256(path),
        container=container,
    )
    if container == "unknown":
        raise IngestError(
            "UNSUPPORTED_FORMAT",
            f"Unsupported file type for '{path.name}'. Supported: CSV/TXT/TSV, MAT (v5/v7), XLS/XLSX, ZIP.",
        )
    if container == "zip":
        tables, images, warnings, skipped, extracted_root = _read_zip(path, extract_dir=extract_images_to)
        result.tables = tables
        result.image_files = images
        result.warnings = warnings
        result.skipped = skipped
        result.extracted_root = extracted_root
        if not tables and not images:
            raise IngestError("EMPTY_ARCHIVE", f"'{path.name}' contains no readable tables or images.")
        return result
    result.tables = _read_single(path)
    if not result.tables:
        raise IngestError("NO_TABLES", f"'{path.name}' produced no readable tables.")
    return result
