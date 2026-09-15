from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import ParsedRow, ParseResult
from .table import dataframe_to_rows


def parse_csv(path: Path) -> ParseResult:
    result = ParseResult(detected_format="csv")
    # Try a few encodings + try to auto-detect header row position.
    for enc in ("utf-8", "utf-16", "latin-1"):
        try:
            df = pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False, on_bad_lines="skip")
            break
        except UnicodeDecodeError:
            continue
        except Exception as exc:
            result.warnings.append(f"csv read with {enc} failed: {exc}")
    else:
        raise ValueError(f"Could not read CSV {path}")

    rows = dataframe_to_rows(df, source_label=path.name, log=result.log, warnings=result.warnings)
    result.rows.extend(rows)
    result.merge_period()
    return result
