"""Tests ModelTrainer — presence dataset et ensure_trained."""

from __future__ import annotations

import pytest

from rod_ia.config.settings import get_settings
from rod_ia.domain.services.model_trainer import ModelTrainer


@pytest.fixture
def trainer():
    settings = get_settings()
    return ModelTrainer(settings.data_processed_dir, settings.artifacts_dir)


def test_dataset_ready_when_processed_files_exist(trainer):
    if not (trainer.processed_dir / "dataset_meta.json").exists():
        pytest.skip("Dataset absent")
    assert trainer.dataset_ready() is True


def test_ensure_trained_idempotent(trainer):
    if not trainer.dataset_ready():
        pytest.skip("Dataset absent")
    if not trainer.is_model_present():
        pytest.skip("Modele absent")
    meta = trainer.ensure_trained(force=False)
    assert meta.get("status") == "already_present"


def test_ensure_trained_raises_without_dataset(tmp_path):
    t = ModelTrainer(tmp_path / "processed", tmp_path / "artifacts")
    with pytest.raises(FileNotFoundError):
        t.ensure_trained()