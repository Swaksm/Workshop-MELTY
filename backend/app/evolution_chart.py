import io
from datetime import datetime

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402

COULEUR_TEMP = "#1f78b4"
COULEUR_GAZ = "#c0392b"


def graphique_evolution(mesures: list, moment_alerte: datetime) -> bytes | None:
    """Rendu PNG de la température et du gaz menant à l'alerte.

    `mesures` : objets avec .received_at, .temp, .gas, triés du plus ancien au plus récent.
    Pas de "après" : le mail part au moment de l'alerte, le futur n'existe pas encore.
    """
    if len(mesures) < 2:
        return None

    temps = [m.received_at for m in mesures]
    valeurs_temp = [m.temp for m in mesures]
    valeurs_gaz = [m.gas for m in mesures]

    fig, ax_temp = plt.subplots(figsize=(5.2, 1.9), dpi=150)
    ax_gaz = ax_temp.twinx()

    ax_temp.plot(temps, valeurs_temp, color=COULEUR_TEMP, linewidth=1.6)
    ax_gaz.plot(temps, valeurs_gaz, color=COULEUR_GAZ, linewidth=1.6)
    ax_temp.axvline(moment_alerte, color=COULEUR_GAZ, linestyle="--", linewidth=1, alpha=0.6)

    ax_temp.set_ylabel("°C", fontsize=8, color=COULEUR_TEMP)
    ax_gaz.set_ylabel("gaz", fontsize=8, color=COULEUR_GAZ)
    ax_temp.tick_params(labelsize=7)
    ax_gaz.tick_params(labelsize=7)
    ax_temp.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))
    fig.autofmt_xdate(rotation=0, ha="center")
    ax_temp.spines["top"].set_visible(False)
    ax_gaz.spines["top"].set_visible(False)
    fig.tight_layout(pad=0.6)

    tampon = io.BytesIO()
    fig.savefig(tampon, format="png", facecolor="white")
    plt.close(fig)
    return tampon.getvalue()
