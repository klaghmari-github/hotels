"""
Couche donnees Excel admin (cache, pagination, mutations).

API publique inchangee pour app.py / sync_data_files :
  get_frame, page_payload, update_rows, add_row, delete_rows,
  reload_dataset, rebuild_joined_data, JOINED_DATASET_ID,
  _cache, _project_to_schema, _save_excel (usage interne / scripts)
"""

from __future__ import annotations

import json
import math
import threading
from pathlib import Path
from typing import Any

import pandas as pd

from schemas import DatasetSchema, get_schema

JOINED_DATASET_ID = "all_data"


class DatasetStore:
    """
    Cache thread-safe des DataFrames Excel + operations CRUD UI.

    Une instance module-level (_STORE) sert toutes les routes Flask.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._cache: dict[str, pd.DataFrame] = {}

    # ------------------------------------------------------------------
    # Serialisation cellules
    # ------------------------------------------------------------------

    @staticmethod
    def cell_to_json(value: Any, *, numeric_null_as_zero: bool = False) -> Any:
        """Cellule pandas → type JSON (arrays Excel inclus)."""
        try:
            if value is None or (isinstance(value, float) and pd.isna(value)):
                return 0 if numeric_null_as_zero else None
            if pd.isna(value):
                return 0 if numeric_null_as_zero else None
        except (TypeError, ValueError):
            pass

        if isinstance(value, (list, tuple)):
            return list(value)
        if hasattr(value, "item") and not isinstance(value, (bytes, str)):
            try:
                value = value.item()
            except Exception:
                pass
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, str):
            text = value.strip().replace("\u00a0", " ").strip()
            if text.lower() in {"", "nan", "none", "<na>"}:
                return ""
            if text.startswith("[") and text.endswith("]"):
                try:
                    return json.loads(text.replace("'", '"'))
                except json.JSONDecodeError:
                    return value
            return text
        return value

    # ------------------------------------------------------------------
    # Charge / projection schema
    # ------------------------------------------------------------------

    @staticmethod
    def project_to_schema(frame: pd.DataFrame, schema: DatasetSchema) -> pd.DataFrame:
        """Aligne le DataFrame sur les colonnes editables du schema."""
        if schema.id == JOINED_DATASET_ID or not schema.editable_columns:
            return frame.copy() if frame is not None else pd.DataFrame()
        cols = list(schema.editable_columns)
        if frame is None or frame.empty:
            return pd.DataFrame(columns=cols)
        data: dict[str, Any] = {}
        n = len(frame)
        for col in cols:
            if col in frame.columns:
                data[col] = frame[col].to_numpy()
            else:
                data[col] = [None] * n
        return pd.DataFrame(data)

    def _ensure_source_files(self, schema: DatasetSchema) -> None:
        """Cree / hydrate les fichiers derives si absents."""
        if schema.id == JOINED_DATASET_ID:
            from join_data import ensure_data_xlsx

            ensure_data_xlsx(force_rebuild=False)
        if schema.id == "model_data":
            from model_data import ensure_model_data

            ensure_model_data(force=False)
        if schema.id == "proximity":
            try:
                from geo_proximity import ensure_hotel_proximity_data

                ensure_hotel_proximity_data(force_refresh=False)
            except Exception:
                pass
        if schema.id == "holidays":
            try:
                from geo_holidays import ensure_hotel_holidays_data

                ensure_hotel_holidays_data(force_refresh=False)
            except Exception:
                pass
        if schema.id == "sales_raw":
            try:
                from sales_prep import ensure_raw_sales_from_archive

                ensure_raw_sales_from_archive()
            except Exception:
                pass

    def load_raw(self, schema: DatasetSchema) -> pd.DataFrame:
        """Lit le fichier Excel du schema (ou squelette vide)."""
        self._ensure_source_files(schema)
        path = schema.path
        if not path.exists():
            return pd.DataFrame(columns=list(schema.editable_columns or []))

        read_kwargs: dict[str, Any] = {}
        if schema.id == JOINED_DATASET_ID:
            from join_data import _NON_NUMERIC_COLS

            read_kwargs["dtype"] = {c: str for c in _NON_NUMERIC_COLS}
        try:
            frame = pd.read_excel(path, sheet_name=schema.sheet, **read_kwargs)
        except ValueError:
            frame = pd.read_excel(path, sheet_name=0, **read_kwargs)

        if schema.id == JOINED_DATASET_ID:
            from join_data import fill_numeric_nulls

            for c in frame.columns:
                if frame[c].dtype == object:
                    frame[c] = frame[c].replace(
                        {"nan": "", "None": "", "<NA>": ""}
                    )
            frame = fill_numeric_nulls(frame)
        return self.project_to_schema(frame, schema)

    def get_frame(self, dataset_id: str, *, reload: bool = False) -> pd.DataFrame:
        """Copie du DataFrame en cache (ou rechargement disque)."""
        with self._lock:
            if reload or dataset_id not in self._cache:
                schema = get_schema(dataset_id)
                self._cache[dataset_id] = self.load_raw(schema)
            return self._cache[dataset_id].copy()

    def invalidate(self, *dataset_ids: str) -> None:
        with self._lock:
            for did in dataset_ids:
                self._cache.pop(did, None)

    def rebuild_joined_data(
        self,
        *,
        fill_weather: bool = False,
        fill_proximity: bool = False,
    ) -> dict[str, Any]:
        """Recalcule all_data.xlsx et met a jour le cache."""
        from join_data import build_joined_dataframe, save_joined_excel

        with self._lock:
            for src_id in (
                "brand",
                "hotel",
                "weather",
                "proximity",
                "sales",
                "holidays",
                JOINED_DATASET_ID,
                "model_data",
            ):
                self._cache.pop(src_id, None)
            frame = build_joined_dataframe(
                fill_weather=fill_weather,
                fill_proximity=fill_proximity,
            )
            path = save_joined_excel(frame)
            self._cache[JOINED_DATASET_ID] = frame
        return {
            "ok": True,
            "path": str(path),
            "filename": path.name,
            "rows": len(frame),
            "columns": list(frame.columns),
            "n_columns": len(frame.columns),
        }

    @staticmethod
    def editable_columns(frame: pd.DataFrame, schema: DatasetSchema) -> list[str]:
        if schema.id == JOINED_DATASET_ID or not schema.editable_columns:
            keys = [c for c in schema.key_columns if c in frame.columns]
            rest = [c for c in frame.columns if c not in keys]
            return keys + rest
        return list(schema.editable_columns)

    # ------------------------------------------------------------------
    # Pagination UI
    # ------------------------------------------------------------------

    def page_payload(
        self,
        dataset_id: str,
        *,
        page: int = 1,
        page_size: int | None = None,
        q: str = "",
    ) -> dict[str, Any]:
        schema = get_schema(dataset_id)
        frame = self.get_frame(dataset_id)
        if dataset_id == JOINED_DATASET_ID:
            from join_data import fill_numeric_nulls

            frame = fill_numeric_nulls(frame)
            with self._lock:
                self._cache[JOINED_DATASET_ID] = frame

        cols = self.editable_columns(frame, schema)
        view = frame[cols].copy() if cols else frame.copy()

        if q and not view.empty:
            mask = pd.Series(False, index=view.index)
            for c in view.columns:
                mask = mask | view[c].astype(str).str.contains(
                    q, case=False, na=False
                )
            view = view[mask]

        total = len(view)
        size = page_size or schema.page_size
        size = max(1, min(int(size), 200))
        pages = max(1, math.ceil(total / size)) if total else 1
        page = max(1, min(int(page), pages))
        start = (page - 1) * size
        end = start + size
        chunk = view.iloc[start:end]
        abs_indices = [int(i) for i in chunk.index.tolist()]

        num_zero = dataset_id == "model_data"
        column_roles: dict[str, str] = {}
        model_stats: dict[str, Any] = {}
        if dataset_id == "model_data":
            from model_data import load_model_data_meta

            md_meta = load_model_data_meta()
            column_roles = dict(md_meta.get("column_roles") or {})
            if "_is_eval" not in column_roles and "_is_eval" in cols:
                column_roles["_is_eval"] = "meta"
            model_stats = {
                "n_id_detail": md_meta.get("n_id_detail"),
                "n_descriptive": md_meta.get("n_descriptive"),
                "n_target": md_meta.get("n_target"),
                "n_train": md_meta.get("n_train"),
                "n_eval": md_meta.get("n_eval"),
                "eval_year": md_meta.get("eval_year"),
                "main_target": md_meta.get("main_target"),
                "id_detail_columns": md_meta.get("id_detail_columns") or [],
                "descriptive_columns": md_meta.get("descriptive_columns") or [],
                "target_columns": md_meta.get("target_columns") or [],
            }
            display_cols = [c for c in cols if c != "_is_eval"]
        else:
            display_cols = cols

        text_null_cols = {
            "hotel_code",
            "hotel_name",
            "nom_hotel",
            "hotel_brand",
            "hotel_city",
            "hotel_adresse_postale_1",
            "hotel_adresse_postale_2",
            "hotel_code_postal",
            "departement",
            "commune",
            "jours_feries",
            "jours_weekend",
            "jours_vacances_scolaires",
            "jours_vacances_hors_feries",
            "jours_holidays",
        }

        rows = []
        for pos, (idx, series) in enumerate(chunk.iterrows()):
            is_eval_row = False
            if "_is_eval" in series.index:
                try:
                    is_eval_row = int(series["_is_eval"]) == 1
                except Exception:
                    is_eval_row = bool(series["_is_eval"])
            row_dict: dict[str, Any] = {
                "_index": int(idx),
                "_row": start + pos + 1,
                "_is_eval": is_eval_row,
            }
            for c in display_cols:
                val = self.cell_to_json(series[c], numeric_null_as_zero=num_zero)
                if num_zero and val is None:
                    if c in text_null_cols:
                        val = "" if not str(c).startswith("jours_") else []
                    else:
                        val = 0
                row_dict[c] = val
            rows.append(row_dict)

        return {
            "dataset_id": dataset_id,
            "label": schema.label,
            "description": schema.description,
            "filename": schema.filename,
            "columns": display_cols,
            "key_columns": [c for c in schema.key_columns if c in display_cols],
            "boolean_columns": [
                c for c in schema.boolean_columns if c in display_cols
            ],
            "array_columns": [c for c in schema.array_columns if c in display_cols],
            "image_columns": [
                c
                for c in getattr(schema, "image_columns", []) or []
                if c in display_cols
            ],
            "column_roles": column_roles,
            "model_stats": model_stats,
            "readonly": bool(schema.readonly),
            "page": page,
            "page_size": size,
            "total_rows": total,
            "total_pages": pages,
            "rows": rows,
            "abs_indices": abs_indices,
        }

    # ------------------------------------------------------------------
    # Coercion + mutations
    # ------------------------------------------------------------------

    @staticmethod
    def coerce_value(col: str, value: Any, schema: DatasetSchema) -> Any:
        if value is None or value == "":
            return None
        if col in schema.array_columns:
            if isinstance(value, list):
                return json.dumps(value, ensure_ascii=False)
            if isinstance(value, str):
                text = value.strip()
                if not text:
                    return "[]"
                if text.startswith("["):
                    return text
                parts = [
                    p.strip()
                    for p in text.replace(";", ",").split(",")
                    if p.strip()
                ]
                return json.dumps(parts, ensure_ascii=False)
            return "[]"
        if col in schema.boolean_columns:
            if isinstance(value, bool):
                return int(value)
            if isinstance(value, (int, float)):
                return int(value)
            s = str(value).strip().lower()
            if s in {"1", "true", "oui", "yes", "x"}:
                return 1
            if s in {"0", "false", "non", "no", ""}:
                return 0
            try:
                return int(float(s))
            except ValueError:
                return 0
        if isinstance(value, (int, float, bool)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text == "":
                return None
            try:
                if "." in text or "e" in text.lower():
                    return float(text)
                return int(text)
            except ValueError:
                return text
        return value

    def save_excel(
        self, dataset_id: str, frame: pd.DataFrame, schema: DatasetSchema
    ) -> Path:
        path = schema.path
        path.parent.mkdir(parents=True, exist_ok=True)
        other_sheets: dict[str, pd.DataFrame] = {}
        if path.exists():
            try:
                xl = pd.ExcelFile(path)
                for name in xl.sheet_names:
                    if name != schema.sheet and name != str(schema.sheet):
                        other_sheets[name] = pd.read_excel(path, sheet_name=name)
            except Exception:
                pass
        to_write = self.project_to_schema(frame, schema)
        sheet_name = schema.sheet if isinstance(schema.sheet, str) else "Sheet1"
        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            to_write.to_excel(writer, index=False, sheet_name=sheet_name)
            for name, df in other_sheets.items():
                df.to_excel(writer, index=False, sheet_name=name[:31])
        return path

    def update_rows(
        self, dataset_id: str, rows: list[dict[str, Any]]
    ) -> dict[str, Any]:
        schema = get_schema(dataset_id)
        with self._lock:
            if dataset_id not in self._cache:
                self._cache[dataset_id] = self.load_raw(schema)
            frame = self._cache[dataset_id]
            editable = set(self.editable_columns(frame, schema))
            for row in rows:
                if "_index" not in row:
                    continue
                idx = int(row["_index"])
                if idx not in frame.index:
                    continue
                for col, val in row.items():
                    if col.startswith("_") or col not in editable:
                        continue
                    if col not in frame.columns:
                        frame[col] = None
                    frame.at[idx, col] = self.coerce_value(col, val, schema)
            self._cache[dataset_id] = frame
            path = self.save_excel(dataset_id, frame, schema)
        return {"ok": True, "saved_to": str(path), "updated": len(rows)}

    def add_row(
        self, dataset_id: str, values: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        schema = get_schema(dataset_id)
        values = values or {}
        with self._lock:
            if dataset_id not in self._cache:
                self._cache[dataset_id] = self.load_raw(schema)
            frame = self._cache[dataset_id]
            editable = self.editable_columns(frame, schema) or list(
                schema.editable_columns
            )
            new: dict[str, Any] = {}
            for col in frame.columns:
                if col in values:
                    new[col] = self.coerce_value(col, values[col], schema)
                else:
                    new[col] = None
            for col in editable:
                if col not in new:
                    new[col] = (
                        self.coerce_value(col, values.get(col), schema)
                        if col in values
                        else None
                    )
            frame = pd.concat([frame, pd.DataFrame([new])], ignore_index=True)
            self._cache[dataset_id] = frame
            path = self.save_excel(dataset_id, frame, schema)
            new_index = int(frame.index[-1])
        return {"ok": True, "index": new_index, "saved_to": str(path)}

    def delete_rows(self, dataset_id: str, indices: list[int]) -> dict[str, Any]:
        schema = get_schema(dataset_id)
        with self._lock:
            if dataset_id not in self._cache:
                self._cache[dataset_id] = self.load_raw(schema)
            frame = self._cache[dataset_id]
            drop = [i for i in indices if i in frame.index]
            frame = frame.drop(index=drop).reset_index(drop=True)
            self._cache[dataset_id] = frame
            path = self.save_excel(dataset_id, frame, schema)
        return {"ok": True, "deleted": len(drop), "saved_to": str(path)}

    def reload_dataset(self, dataset_id: str) -> dict[str, Any]:
        frame = self.get_frame(dataset_id, reload=True)
        schema = get_schema(dataset_id)
        return {
            "ok": True,
            "rows": len(frame),
            "columns": list(frame.columns),
            "editable": self.editable_columns(frame, schema),
        }


# Instance unique + facades module (API historique)
_STORE = DatasetStore()

# Acces direct au cache (sync_data_files / app invalidations)
_cache = _STORE._cache
_lock = _STORE._lock


def _cell_to_json(value: Any, *, numeric_null_as_zero: bool = False) -> Any:
    return DatasetStore.cell_to_json(value, numeric_null_as_zero=numeric_null_as_zero)


def _project_to_schema(frame: pd.DataFrame, schema: DatasetSchema) -> pd.DataFrame:
    return DatasetStore.project_to_schema(frame, schema)


def _load_raw(schema: DatasetSchema) -> pd.DataFrame:
    return _STORE.load_raw(schema)


def get_frame(dataset_id: str, *, reload: bool = False) -> pd.DataFrame:
    return _STORE.get_frame(dataset_id, reload=reload)


def rebuild_joined_data(
    *,
    fill_weather: bool = False,
    fill_proximity: bool = False,
) -> dict[str, Any]:
    return _STORE.rebuild_joined_data(
        fill_weather=fill_weather, fill_proximity=fill_proximity
    )


def _ensure_editable_cols(frame: pd.DataFrame, schema: DatasetSchema) -> list[str]:
    return DatasetStore.editable_columns(frame, schema)


def page_payload(
    dataset_id: str,
    *,
    page: int = 1,
    page_size: int | None = None,
    q: str = "",
) -> dict[str, Any]:
    return _STORE.page_payload(
        dataset_id, page=page, page_size=page_size, q=q
    )


def _coerce_value(col: str, value: Any, schema: DatasetSchema) -> Any:
    return DatasetStore.coerce_value(col, value, schema)


def update_rows(dataset_id: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return _STORE.update_rows(dataset_id, rows)


def add_row(dataset_id: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
    return _STORE.add_row(dataset_id, values)


def delete_rows(dataset_id: str, indices: list[int]) -> dict[str, Any]:
    return _STORE.delete_rows(dataset_id, indices)


def reload_dataset(dataset_id: str) -> dict[str, Any]:
    return _STORE.reload_dataset(dataset_id)


def _save_excel(
    dataset_id: str, frame: pd.DataFrame, schema: DatasetSchema
) -> Path:
    return _STORE.save_excel(dataset_id, frame, schema)
