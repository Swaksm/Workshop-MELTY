from pathlib import Path

import joblib
import numpy as np
from sklearn.neighbors import LocalOutlierFactor
from sklearn.pipeline import Pipeline, make_pipeline
from sklearn.preprocessing import StandardScaler

WINDOW = 30
MIN_TRAINING_SAMPLES = 100
MODEL_DIR = Path("models")

_cache: dict[str, Pipeline] = {}


def _features(values: np.ndarray, i: int) -> list[float]:
    segment = values[max(0, i - WINDOW + 1) : i + 1]
    x = np.arange(len(segment))
    if len(segment) >= 2:
        slope_temp = np.polyfit(x, segment[:, 0], 1)[0]
        slope_gas = np.polyfit(x, segment[:, 2], 1)[0]
    else:
        slope_temp = slope_gas = 0.0
    temp, hum, gas = values[i]
    return [temp, hum, gas, slope_temp, slope_gas]


def _new_model() -> Pipeline:
    return make_pipeline(
        StandardScaler(),
        LocalOutlierFactor(n_neighbors=20, novelty=True, contamination=0.05),
    )


def train(table_id: str, values: np.ndarray) -> None:
    X = np.array([_features(values, i) for i in range(len(values))])
    model = _new_model().fit(X)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, MODEL_DIR / f"{table_id}.joblib")
    _cache[table_id] = model


def get_model(table_id: str) -> Pipeline | None:
    if table_id not in _cache:
        path = MODEL_DIR / f"{table_id}.joblib"
        if not path.exists():
            return None
        _cache[table_id] = joblib.load(path)
    return _cache[table_id]


def is_anomaly(model: Pipeline, values: np.ndarray) -> bool:
    return model.predict([_features(values, len(values) - 1)])[0] == -1


NOMS_CARACTERISTIQUES = ["température", "humidité", "gaz", "pente de la température", "pente du gaz"]


def explication(model: Pipeline, values: np.ndarray) -> dict:
    f = _features(values, len(values) - 1)
    scaler = model.named_steps["standardscaler"]
    ecarts = (np.array(f) - scaler.mean_) / scaler.scale_
    lof = float(-model.score_samples([f])[0])
    return {
        "modele": "LOF",
        "facteur_lof": round(lof, 2),
        "caracteristiques": [
            {
                "nom": nom,
                "valeur": round(float(valeur), 3),
                "normal": round(float(moyenne), 3),
                "ecart": round(float(ecart), 1),
            }
            for nom, valeur, moyenne, ecart in zip(NOMS_CARACTERISTIQUES, f, scaler.mean_, ecarts)
        ],
    }
