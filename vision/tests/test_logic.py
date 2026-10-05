from logic import categorize


def test_personne_detectee():
    assert categorize("person", 0.9) == "person"


def test_animal_detecte():
    assert categorize("dog", 0.8) == "animal"


def test_autre_objet_ignore():
    assert categorize("car", 0.9) is None


def test_confiance_trop_faible_ignoree():
    assert categorize("person", 0.3) is None
