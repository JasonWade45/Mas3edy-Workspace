SUPPORTED_LANGUAGES = {"ar": "العربية", "en": "English"}


def normalize_language(value: object) -> str:
    """Return a supported UI language code, defaulting to Arabic."""
    return value if isinstance(value, str) and value in SUPPORTED_LANGUAGES else "ar"


def translate(arabic: str, english: str, language: str = "ar") -> str:
    """Pick a localized UI string without changing stable internal identifiers."""
    return english if normalize_language(language) == "en" else arabic


def text_direction(language: str) -> str:
    return "ltr" if normalize_language(language) == "en" else "rtl"
