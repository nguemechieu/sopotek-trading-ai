import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from frontend.ui.i18n import normalize_language_code, translate


def test_normalize_language_code_falls_back_to_base_language():
    assert normalize_language_code("fr-FR") == "fr"
    assert normalize_language_code("es-419") == "es"


def test_translate_uses_requested_language_and_english_fallback():
    assert translate("fr", "terminal.menu.file") == "Fichier"
    assert translate("de", "terminal.menu.file") == "File"
    assert translate("en", "missing.key") == "missing.key"
