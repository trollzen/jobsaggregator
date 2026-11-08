"""Storage: CSV (development) and Google Sheets (production).

Both stores write by column NAME, never by position, so the user may add own
columns or reorder them. Only new rows are appended; existing rows (and the
manual "Статус") are never touched.
"""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Protocol

from jobagg.models import FIELD_BY_HEADER, HEADER, STATUS_VALUES, Job, job_to_cell, row_to_job


class Store(Protocol):
    def load_jobs(self) -> list[Job]: ...
    def append(self, jobs: list[Job]) -> int: ...
    def load_state(self) -> dict[str, int]: ...
    def save_state(self, state: dict[str, int]) -> None: ...


def build_rows(header: list[str], jobs: list[Job]) -> list[list]:
    rows = []
    for job in jobs:
        row = []
        for h in header:
            field = FIELD_BY_HEADER.get(h)
            row.append(job_to_cell(job, field) if field else "")
        rows.append(row)
    return rows


class CsvStore:
    def __init__(self, path: str = "out/jobs.csv", state_path: str = "out/state.json"):
        self.path = Path(path)
        self.state_path = Path(state_path)

    def _read(self) -> tuple[list[str], list[list[str]]]:
        if not self.path.exists():
            return [], []
        with open(self.path, encoding="utf-8", newline="") as f:
            rows = list(csv.reader(f))
        return (rows[0], rows[1:]) if rows else ([], [])

    def load_jobs(self) -> list[Job]:
        header, rows = self._read()
        return [row_to_job(header, r) for r in rows]

    def append(self, jobs: list[Job]) -> int:
        if not jobs:
            return 0
        header, _ = self._read()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        new_file = not header
        if new_file:
            header = HEADER
        with open(self.path, "a", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            if new_file:
                w.writerow(header)
            w.writerows(build_rows(header, jobs))
        return len(jobs)

    def load_state(self) -> dict[str, int]:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        return {}

    def save_state(self, state: dict[str, int]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
        )


class SheetsStore:
    """Google Sheets via service account.

    Env: SHEET_ID, and GOOGLE_SA_JSON (JSON text) or GOOGLE_SA_FILE (path).
    gspread's BackOffHTTPClient retries on 429/5xx.
    """

    def __init__(
        self,
        sheet_id: str | None = None,
        tab: str = "Вакансии",
        state_tab: str = "_state",
        client=None,
    ):
        import gspread

        sheet_id = sheet_id or os.environ["SHEET_ID"]
        if client is None:
            if os.environ.get("GOOGLE_SA_JSON"):
                info = json.loads(os.environ["GOOGLE_SA_JSON"])
                client = gspread.service_account_from_dict(
                    info, http_client=gspread.BackOffHTTPClient
                )
            else:
                client = gspread.service_account(
                    filename=os.environ.get("GOOGLE_SA_FILE", "service_account.json"),
                    http_client=gspread.BackOffHTTPClient,
                )
        self.sh = client.open_by_key(sheet_id)
        self.ws = self._worksheet(tab, len(HEADER))
        self.state_ws = self._worksheet(state_tab, 2, hidden=True)
        self._header: list[str] | None = None

    def _worksheet(self, title: str, cols: int, hidden: bool = False):
        import gspread

        try:
            return self.sh.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self.sh.add_worksheet(title=title, rows=100, cols=cols)
            if hidden:
                ws.hide()
            return ws

    def ensure_header(self) -> list[str]:
        if self._header is not None:
            return self._header
        header = self.ws.row_values(1)
        if not header:
            self.ws.update(range_name="A1", values=[HEADER])
            self.ws.freeze(rows=1)
            self._add_status_validation(HEADER)
            header = list(HEADER)
        else:
            missing = [h for h in HEADER if h not in header]
            if missing:  # add our missing columns at the end, keep user's layout
                start = len(header)
                if self.ws.col_count < start + len(missing):
                    self.ws.add_cols(start + len(missing) - self.ws.col_count)
                self.ws.update(range_name=_a1(1, start + 1), values=[missing])
                header = header + missing
        self._header = header
        return header

    def _add_status_validation(self, header: list[str]) -> None:
        col = header.index("Статус")
        self.sh.batch_update(
            {
                "requests": [
                    {
                        "setDataValidation": {
                            "range": {
                                "sheetId": self.ws.id,
                                "startRowIndex": 1,
                                "startColumnIndex": col,
                                "endColumnIndex": col + 1,
                            },
                            "rule": {
                                "condition": {
                                    "type": "ONE_OF_LIST",
                                    "values": [{"userEnteredValue": v} for v in STATUS_VALUES],
                                },
                                "showCustomUi": True,
                                "strict": False,
                            },
                        }
                    }
                ]
            }
        )

    def load_jobs(self) -> list[Job]:
        header = self.ensure_header()
        rows = self.ws.get_all_values()[1:]  # one read per run
        return [row_to_job(header, r) for r in rows]

    def append(self, jobs: list[Job]) -> int:
        if not jobs:
            return 0
        header = self.ensure_header()
        self.ws.append_rows(
            build_rows(header, jobs),
            value_input_option="RAW",
            insert_data_option="INSERT_ROWS",
            table_range="A1",
        )
        return len(jobs)

    def load_state(self) -> dict[str, int]:
        state = {}
        for row in self.state_ws.get_all_values():
            if len(row) >= 2 and row[1].strip().isdigit():
                state[row[0]] = int(row[1])
        return state

    def save_state(self, state: dict[str, int]) -> None:
        values = [["channel", "last_message_id"]] + [[k, v] for k, v in sorted(state.items())]
        self.state_ws.clear()
        self.state_ws.update(range_name="A1", values=values)


def _a1(row: int, col: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def make_store(cfg: dict) -> Store:
    kind = cfg.get("type", "csv")
    if kind == "sheets":
        return SheetsStore(
            tab=cfg.get("sheet_tab", "Вакансии"), state_tab=cfg.get("state_tab", "_state")
        )
    if kind == "csv":
        return CsvStore(
            cfg.get("csv_path", "out/jobs.csv"), cfg.get("state_path", "out/state.json")
        )
    raise ValueError(f"unknown store type: {kind}")
