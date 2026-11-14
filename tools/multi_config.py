"""Tell whether CMake presets and caches use a multi-configuration generator."""

MULTI_CONFIG_GENERATORS = ("Ninja Multi-Config", "Xcode")
MULTI_CONFIG_GENERATOR_PREFIXES = ("Visual Studio",)
GENERATOR_ENTRY = "CMAKE_GENERATOR:INTERNAL="


class SingleConfigError(Exception):
    """Report a build that does not use a multi-configuration generator."""


def find_generator(project_presets, preset_name):
    """Return the generator of a configure preset or its parents, or None."""
    presets = {p["name"]: p for p in project_presets.get("configurePresets", [])}
    return _find_generator(presets, preset_name)


def is_multi_config_generator(generator):
    """Return True if the generator builds several configurations."""
    if generator is None:
        return False
    return generator in MULTI_CONFIG_GENERATORS or generator.startswith(
        MULTI_CONFIG_GENERATOR_PREFIXES
    )


def cache_is_multi_config(cache_text):
    """Return True if the CMakeCache.txt text comes from a multi-config generator."""
    return is_multi_config_generator(_cache_generator(cache_text))


def _cache_generator(cache_text):
    """Return the generator that CMakeCache.txt records, or None."""
    for line in cache_text.splitlines():
        if line.startswith(GENERATOR_ENTRY):
            return line.removeprefix(GENERATOR_ENTRY)
    return None


def _find_generator(presets, preset_name):
    """Search the preset, then its parents in order, for a generator."""
    preset = presets.get(preset_name)
    if preset is None:
        return None
    if "generator" in preset:
        return preset["generator"]
    for parent in _parents(preset):
        generator = _find_generator(presets, parent)
        if generator is not None:
            return generator
    return None


def _parents(preset):
    """Return the names of the parent presets as a list."""
    inherits = preset.get("inherits", [])
    return [inherits] if isinstance(inherits, str) else inherits
