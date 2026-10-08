"""État partagé du buzzer et de la LED, par table.

Mis à jour à chaque commande reçue (dashboard ou détection automatique) et
relu par toutes les interfaces via /etat : un clic sur un poste se répercute
sur les autres au prochain rafraîchissement (quelques secondes), sans état
propre à chaque navigateur. Repart à zéro si le backend redémarre, comme
l'état réel du buzzer sur l'ESP32 (buzzerManual) après un reboot.
"""

_etat: dict[str, dict[str, bool]] = {}


def _table(table_id: str) -> dict[str, bool]:
    return _etat.setdefault(table_id, {"buzzer": False, "buzzer_muet": False, "led": False})


def appliquer_buzzer(table_id: str, commande: str) -> None:
    if commande in ("on", "off"):
        _table(table_id)["buzzer"] = commande == "on"
    elif commande in ("mute", "unmute"):
        _table(table_id)["buzzer_muet"] = commande == "mute"
    # "test" et "silence" sont ponctuels : ils ne changent pas l'état affiché.


def appliquer_led(table_id: str, commande: str) -> None:
    if commande in ("on", "off"):
        _table(table_id)["led"] = commande == "on"
    # "test" est ponctuel.


def lire(table_id: str) -> dict[str, bool]:
    return dict(_table(table_id))
