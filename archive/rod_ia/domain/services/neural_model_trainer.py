"""Réseau de neurones Keras — comparaison avec XGBoost (non utilisé en production)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

MONTHS = 12
SEASONAL_DIM = 4  # sin/cos fondamentaux + harmonique


def _seasonal_encoding(n_months: int = MONTHS) -> np.ndarray:
    """Encodage cyclique explicite des mois (prior saisonnier sans sur-apprendre)."""
    angles = 2.0 * np.pi * np.arange(n_months) / n_months
    return np.column_stack(
        [
            np.sin(angles),
            np.cos(angles),
            np.sin(2.0 * angles),
            np.cos(2.0 * angles),
        ]
    ).astype(np.float32)


def _seasonal_encoding_layer_class():
    import keras
    from keras import layers

    class SeasonalEncodingLayer(layers.Layer):
        """Couche sérialisable — diffuse l'encodage mensuel sur le batch."""

        def __init__(self, n_months: int = MONTHS, seasonal_dim: int = SEASONAL_DIM, **kwargs):
            super().__init__(**kwargs)
            self.n_months = n_months
            self.seasonal_dim = seasonal_dim

        def build(self, input_shape):
            init = _seasonal_encoding(self.n_months)
            self.seasonal_codes = self.add_weight(
                name="seasonal_codes",
                shape=(self.n_months, self.seasonal_dim),
                initializer=keras.initializers.Constant(init),
                trainable=False,
            )

        def call(self, hotel_seq):
            import tensorflow as tf

            batch = tf.shape(hotel_seq)[0]
            return tf.tile(tf.expand_dims(self.seasonal_codes, 0), [batch, 1, 1])

        def get_config(self):
            config = super().get_config()
            config.update(
                {"n_months": self.n_months, "seasonal_dim": self.seasonal_dim}
            )
            return config

    keras.saving.register_keras_serializable(package="rod_ia")(SeasonalEncodingLayer)
    return SeasonalEncodingLayer


SeasonalEncodingLayer = _seasonal_encoding_layer_class()


def build_seasonal_dual_tower_model(n_features: int, n_months: int = MONTHS):
    """Architecture compacte pour petits jeux de données hôteliers.

    - Projection 184D → 32D (réduit le risque de sur-apprentissage)
    - Tronc résiduel léger
    - Encodage saisonnier sin/cos fixe, répété sur 12 mois
    - Conv1D : cohérence temporelle entre mois voisins
    - 2 sorties par mois (CA, ventes) avec softplus
    """
    import keras
    from keras import layers, regularizers

    l2 = regularizers.l2(1e-2)
    inputs = keras.Input(shape=(n_features,), name="hotel_features")

    x = layers.Dense(32, kernel_regularizer=l2, name="input_proj")(inputs)
    x = layers.BatchNormalization(name="input_bn")(x)
    x = layers.Dropout(0.5, name="dropout_input")(x)

    skip = layers.Dense(32, use_bias=False, kernel_regularizer=l2, name="skip_proj")(x)
    x = layers.Dense(32, activation="swish", kernel_regularizer=l2, name="encoder")(x)
    trunk = layers.Add(name="residual_add")([skip, x])
    hotel_vec = layers.LayerNormalization(name="hotel_norm")(trunk)

    hotel_seq = layers.RepeatVector(n_months, name="repeat_months")(hotel_vec)
    seasonal_seq = SeasonalEncodingLayer(n_months=n_months, name="seasonal_encoding")(
        hotel_seq
    )
    combined = layers.Concatenate(name="month_context")([hotel_seq, seasonal_seq])

    seq = layers.Conv1D(
        16,
        kernel_size=3,
        padding="same",
        activation="swish",
        kernel_regularizer=l2,
        name="temporal_conv_1",
    )(combined)
    seq = layers.Dropout(0.4, name="dropout_conv")(seq)
    seq = layers.Conv1D(
        8,
        kernel_size=3,
        padding="same",
        activation="swish",
        kernel_regularizer=l2,
        name="temporal_conv_2",
    )(seq)

    per_month = layers.Dense(2, activation="softplus", name="ca_ventes_per_month")(seq)
    outputs = layers.Reshape((n_months * 2,), name="interleaved_targets")(per_month)

    return keras.Model(inputs=inputs, outputs=outputs, name="seasonal_dual_tower")


def load_neural_model(path: Path):
    """Charge le modèle Keras avec les objets custom du package rod_ia."""
    import keras

    _ = SeasonalEncodingLayer  # enregistre la couche custom avant chargement
    return keras.models.load_model(path)


@dataclass
class NeuralPreprocessor:
    feature_scaler: StandardScaler
    target_scaler: StandardScaler
    use_log1p_targets: bool = True

    def transform_features(self, x: np.ndarray) -> np.ndarray:
        return self.feature_scaler.transform(x)

    def transform_targets(self, y: np.ndarray) -> np.ndarray:
        if self.use_log1p_targets:
            y = np.log1p(np.maximum(y, 0.0))
        return self.target_scaler.transform(y)

    def inverse_targets(self, y_scaled: np.ndarray) -> np.ndarray:
        y = self.target_scaler.inverse_transform(y_scaled)
        if self.use_log1p_targets:
            y = np.expm1(y)
        return np.maximum(y, 0.0)


class NeuralModelTrainer:
    """Entraîne et persiste un réseau Keras pour benchmark contre XGBoost."""

    MODEL_FILE = "neural_model.keras"
    PREPROCESSOR_FILE = "neural_preprocessor.joblib"

    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = Path(artifacts_dir)
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    @property
    def model_path(self) -> Path:
        return self.artifacts_dir / self.MODEL_FILE

    @property
    def preprocessor_path(self) -> Path:
        return self.artifacts_dir / self.PREPROCESSOR_FILE

    def is_available(self) -> bool:
        try:
            import tensorflow  # noqa: F401
        except ImportError:
            return False
        return True

    @staticmethod
    def _augment(
        x: np.ndarray,
        y: np.ndarray,
        *,
        copies: int = 4,
        noise_std: float = 0.03,
        seed: int = 42,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Bruit gaussien léger — compense le faible nombre d'hôtels."""
        rng = np.random.default_rng(seed)
        xs = [x]
        ys = [y]
        for _ in range(copies):
            noise = rng.normal(0.0, noise_std, size=x.shape).astype(np.float32)
            xs.append(x + noise)
            ys.append(y)
        return np.vstack(xs), np.vstack(ys)

    @staticmethod
    def _mae(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        return float(np.mean(np.abs(y_true - y_pred)))

    def _leave_one_out_mae(
        self,
        x: np.ndarray,
        y: np.ndarray,
        *,
        epochs: int,
        seed: int,
    ) -> float | None:
        if len(x) < 3:
            return None

        import tensorflow as tf
        from tensorflow import keras

        errors: list[float] = []
        for holdout in range(len(x)):
            train_mask = np.ones(len(x), dtype=bool)
            train_mask[holdout] = False
            x_train, y_train = x[train_mask], y[train_mask]
            x_val, y_val = x[holdout : holdout + 1], y[holdout : holdout + 1]

            prep = NeuralPreprocessor(
                feature_scaler=StandardScaler().fit(x_train),
                target_scaler=StandardScaler().fit(
                    np.log1p(np.maximum(y_train, 0.0))
                ),
            )
            x_aug, y_aug = self._augment(
                prep.transform_features(x_train),
                prep.transform_targets(y_train),
                seed=seed + holdout,
            )

            tf.keras.utils.set_random_seed(seed + holdout)
            model = build_seasonal_dual_tower_model(x.shape[1])
            model.compile(optimizer=keras.optimizers.Adam(learning_rate=5e-4), loss="huber")
            model.fit(
                x_aug,
                y_aug,
                epochs=epochs,
                batch_size=max(2, min(4, len(x_aug))),
                verbose=0,
            )
            pred = prep.inverse_targets(
                model.predict(prep.transform_features(x_val), verbose=0)
            )
            errors.append(self._mae(y_val, pred))

        return float(np.mean(errors))

    def train(
        self,
        x_train: pd.DataFrame,
        y_train: pd.DataFrame,
        *,
        epochs: int = 400,
        seed: int = 42,
    ) -> dict:
        if not self.is_available():
            return {
                "status": "skipped",
                "reason": "tensorflow absent — pip install tensorflow",
            }

        import tensorflow as tf
        from tensorflow import keras

        tf.keras.utils.set_random_seed(seed)

        x_np = x_train.values.astype(np.float32)
        y_np = y_train.values.astype(np.float32)

        preprocessor = NeuralPreprocessor(
            feature_scaler=StandardScaler().fit(x_np),
            target_scaler=StandardScaler().fit(np.log1p(np.maximum(y_np, 0.0))),
        )
        x_scaled = preprocessor.transform_features(x_np)
        y_scaled = preprocessor.transform_targets(y_np)
        x_aug, y_aug = self._augment(x_scaled, y_scaled, seed=seed)

        model = build_seasonal_dual_tower_model(x_np.shape[1])
        model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=5e-4),
            loss=keras.losses.Huber(delta=1.0),
        )
        history = model.fit(
            x_aug,
            y_aug,
            epochs=epochs,
            batch_size=max(2, min(6, len(x_aug))),
            verbose=0,
            callbacks=[
                keras.callbacks.EarlyStopping(
                    monitor="loss",
                    patience=60,
                    restore_best_weights=True,
                )
            ],
        )

        train_pred = preprocessor.inverse_targets(model.predict(x_scaled, verbose=0))
        train_mae = self._mae(y_np, train_pred)
        loocv_mae = self._leave_one_out_mae(x_np, y_np, epochs=min(150, epochs), seed=seed)

        model.save(self.model_path)
        joblib.dump(preprocessor, self.preprocessor_path)

        n_params = int(model.count_params())
        return {
            "status": "trained",
            "architecture": "seasonal_dual_tower",
            "description": (
                "Projection 32D + tronc résiduel + encodage saisonnier sin/cos "
                "+ Conv1D temporelle + sorties CA/ventes par mois (softplus)"
            ),
            "n_params": n_params,
            "epochs_run": len(history.history.get("loss", [])),
            "train_mae": train_mae,
            "loocv_mae": loocv_mae,
            "use_log1p_targets": preprocessor.use_log1p_targets,
            "model_path": str(self.model_path),
        }

    def load_meta_fragment(self) -> dict:
        if not self.model_path.exists():
            return {"status": "absent"}
        return {
            "status": "present",
            "model_path": str(self.model_path),
            "preprocessor_path": str(self.preprocessor_path),
        }