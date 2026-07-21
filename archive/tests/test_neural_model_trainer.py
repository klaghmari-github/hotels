"""Tests réseau de neurones Keras — architecture et benchmark."""

from __future__ import annotations

import pytest

from rod_ia.config.settings import get_settings
from rod_ia.domain.services.model_trainer import ModelTrainer
from rod_ia.domain.services.neural_model_trainer import (
    NeuralModelTrainer,
    build_seasonal_dual_tower_model,
)


@pytest.fixture
def neural_trainer():
    settings = get_settings()
    return NeuralModelTrainer(settings.artifacts_dir)


def test_build_seasonal_dual_tower_model():
    tf = pytest.importorskip("tensorflow")
    model = build_seasonal_dual_tower_model(n_features=32, n_months=12)
    assert model.count_params() > 0
    out = model.predict(tf.zeros((2, 32)), verbose=0)
    assert out.shape == (2, 24)


def test_neural_train_on_dataset(neural_trainer):
    pytest.importorskip("tensorflow")
    settings = get_settings()
    trainer = ModelTrainer(settings.data_processed_dir, settings.artifacts_dir)
    if not trainer.dataset_ready():
        pytest.skip("Dataset absent")
    x_train, y_train, _, _ = trainer._load_dataset()
    meta = neural_trainer.train(x_train, y_train, epochs=80)
    assert meta.get("status") == "trained"
    assert meta.get("train_mae") is not None
    assert neural_trainer.model_path.exists()


def test_meta_includes_neural_comparison():
    pytest.importorskip("tensorflow")
    settings = get_settings()
    trainer = ModelTrainer(settings.data_processed_dir, settings.artifacts_dir)
    if not trainer.dataset_ready():
        pytest.skip("Dataset absent")
    meta = trainer.train()
    assert "model_comparison" in meta
    assert "neural_network" in meta
    assert meta.get("production_model") == "xgboost"