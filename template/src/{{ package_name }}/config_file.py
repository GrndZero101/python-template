"""The user's YAML config file: where it lives, and the settings source that reads it.

The file sits between the environment and the field defaults, so a setting resolves flag, then
environment variable, then config file, then default. Its keys are the field names of `Settings`:

    output: json
    verbose: true

`--config PATH` or the `<PREFIX>CONFIG` variable names the file; otherwise it is
`default_config_path`, which need not exist. Why YAML, and why this location:
.claude/skills/python-cli-modern/reference/configuration.md.
"""

import os
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import yaml
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

CONFIG_FILE_NAME = "config.yaml"
# The setting that names the file. It is resolved before the file is read, so the file cannot set it.
CONFIG_FIELD = "config"


class ConfigFileError(ValueError):
    """The named config file is missing, is not a YAML mapping, or has a key that is no setting."""


def default_config_path(
    app_name: str,
    *,
    environ: Mapping[str, str] = os.environ,
    platform: str = sys.platform,
    home: Callable[[], Path] = Path.home,
) -> Path:
    """Return where `app_name` looks for its config file when nothing names one.

    `$XDG_CONFIG_HOME` wins on every platform when it is absolute, as the XDG spec requires.
    Otherwise `%APPDATA%` on Windows, the roaming profile, so settings follow the user; and
    `~/.config` everywhere else, macOS included, which is where CLI users look.
    """
    xdg = environ.get("XDG_CONFIG_HOME", "")
    if xdg and Path(xdg).is_absolute():
        base = Path(xdg)
    elif platform == "win32":
        appdata = environ.get("APPDATA", "")
        base = Path(appdata) if appdata else home() / "AppData" / "Roaming"
    else:
        base = home() / ".config"
    return base / app_name / CONFIG_FILE_NAME


def read_config_file(settings_cls: type[BaseSettings], path: Path) -> dict[str, Any]:
    """Return the settings in the YAML file at `path`, rejecting any key that is not a setting.

    Values are returned as parsed: pydantic validates them with every other source's.
    """
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        msg = f"config file {path} is not valid YAML: {exc}"
        raise ConfigFileError(msg) from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        kind = type(loaded).__name__
        msg = f"config file {path} must map setting names to values, not hold a {kind}"
        raise ConfigFileError(msg)
    values: dict[str, Any] = loaded
    known = sorted(name for name in settings_cls.model_fields if name != CONFIG_FIELD)
    unknown = sorted(str(key) for key in values if key not in known)
    if unknown:
        msg = (
            f"config file {path}: {', '.join(unknown)} is not a setting; "
            f"the settings are {', '.join(known)}"
        )
        raise ConfigFileError(msg)
    return values


class ConfigFileSource(PydanticBaseSettingsSource):
    """Settings from the config file, for `Settings.settings_customise_sources`.

    List it after the init and environment sources: by then `current_state` holds `config` if a
    flag or the variable gave it. A file named that way must exist; the default need not.
    """

    def __init__(self, settings_cls: type[BaseSettings], default: Path) -> None:
        """Read `config` from the earlier sources, falling back to `default`."""
        super().__init__(settings_cls)
        self.default = default

    def get_field_value(self, field: FieldInfo, field_name: str) -> tuple[Any, str, bool]:
        """Unused, but abstract: `__call__` reads the whole file at once."""
        del field
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        """Return the file's settings, or none when the default file does not exist."""
        given = self.current_state.get(CONFIG_FIELD)
        path = Path(given) if given is not None else self.default
        if path.is_file():
            return read_config_file(self.settings_cls, path)
        if given is None:
            return {}
        msg = f"config file {path} is not a file; fix the path given by --config or its variable"
        raise ConfigFileError(msg)
