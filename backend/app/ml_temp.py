import numpy as np
from sklearn.ensemble import RandomForestClassifier

WINDOW = 30
SEUIL = 0.8
_rng = np.random.default_rng(42)


def _features(serie: np.ndarray) -> list[float]:
    x = np.arange(len(serie))
    pente = np.polyfit(x, serie, 1)[0]
    pente_recente = np.polyfit(x[-10:], serie[-10:], 1)[0]
    variation = serie[-1] - serie[0]
    return [pente, pente_recente, variation, serie.std()]


def _serie(debut: float, pente: float, bruit: float) -> np.ndarray:
    return debut + pente * np.arange(WINDOW) + _rng.normal(0, bruit, WINDOW)


def _jeu_simule(par_classe: int = 2000) -> tuple[np.ndarray, np.ndarray]:
    X, y = [], []
    for _ in range(par_classe):
        serie = _serie(_rng.uniform(15, 35), _rng.normal(0, 0.003), _rng.uniform(0.05, 0.4))
        X.append(_features(serie))
        y.append(0)
    for _ in range(par_classe):
        serie = _serie(_rng.uniform(15, 35), _rng.uniform(0.03, 0.3), _rng.uniform(0.05, 0.4))
        X.append(_features(serie))
        y.append(1)
    for _ in range(par_classe // 2):
        serie = _serie(_rng.uniform(15, 35), -_rng.uniform(0.03, 0.3), _rng.uniform(0.05, 0.4))
        X.append(_features(serie))
        y.append(0)
    return np.array(X), np.array(y)


_X, _y = _jeu_simule()
_modele = RandomForestClassifier(n_estimators=150, max_depth=8, random_state=42).fit(_X, _y)


def probabilite_hausse(serie: np.ndarray) -> float:
    return float(_modele.predict_proba([_features(serie)])[0][1])


NOMS_CARACTERISTIQUES = ["pente", "pente récente (10 dernières mesures)", "variation totale", "écart-type"]
REFERENCES = [0.0, 0.0, 0.0, None]


def explication(serie: np.ndarray) -> dict:
    f = _features(serie)
    return {
        "modele": "Random Forest",
        "probabilite": round(float(_modele.predict_proba([f])[0][1]), 3),
        "caracteristiques": [
            {"nom": nom, "valeur": round(float(valeur), 3), "normal": reference}
            for nom, valeur, reference in zip(NOMS_CARACTERISTIQUES, f, REFERENCES)
        ],
    }
