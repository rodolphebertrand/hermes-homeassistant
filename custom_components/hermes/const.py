"""Constants for the Hermes integration."""

DOMAIN = "hermes"

# Configuration keys
CONF_HOST = "host"
CONF_PORT = "port"
CONF_API_KEY = "api_key"
CONF_TIMEOUT = "timeout"
CONF_STRIP_EMOJIS = "strip_emojis"
CONF_TTS_MAX_CHARS = "tts_max_chars"
CONF_AGENT = "agent"

# Defaults
DEFAULT_HOST = "192.168.1.112"
DEFAULT_PORT = 8642
DEFAULT_TIMEOUT = 60
DEFAULT_STRIP_EMOJIS = True
DEFAULT_TTS_MAX_CHARS = 0
DEFAULT_AGENT = "ha"

# Agents available on the Hermes server (edit to match `~/.hermes/profiles/`).
# "default" uses the gateway's main profile (no /p/<agent>/ prefix).
AVAILABLE_AGENTS = [
    "default",
    "ha",
    "pi",
    "alex",
    "alex3",
    "apic",
    "coach",
    "coder",
    "lea",
    "main",
    "reminder",
    "tech-watch",
]
