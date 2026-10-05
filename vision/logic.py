PERSON = "person"
ANIMALS = {"bird", "cat", "dog", "horse", "sheep", "cow", "elephant", "bear", "zebra", "giraffe"}
MIN_CONFIDENCE = 0.5


def categorize(label: str, confidence: float) -> str | None:
    if confidence < MIN_CONFIDENCE:
        return None
    if label == PERSON:
        return "person"
    if label in ANIMALS:
        return "animal"
    return None
