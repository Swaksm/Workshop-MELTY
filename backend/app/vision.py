import threading
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.alerts_mail import decoder_image
from app.models import Detection
from app.notifier import notifier
from app.schemas import DetectionIn

BUZZER_DURATION = 10.0
_timers: dict[str, threading.Timer] = {}


def record_person(
    session: Session,
    table_id: str,
    detection: DetectionIn,
    set_buzzer: Callable[[str, str], None],
) -> None:
    session.add(
        Detection(table_id=table_id, label=detection.label, confidence=detection.confidence)
    )
    session.commit()

    set_buzzer(table_id, "on")
    previous = _timers.pop(table_id, None)
    if previous is not None:
        previous.cancel()
    timer = threading.Timer(BUZZER_DURATION, set_buzzer, args=(table_id, "off"))
    timer.daemon = True
    _timers[table_id] = timer
    timer.start()

    notifier.personne(table_id, detection.confidence, decoder_image(detection.image))
