"""K100DRA — an AI short-form video *creator*, not just a generator.

A Reddit story becomes a scripted, voiced, captioned, branded vertical video in
the voice of the K100DRA persona, and you watch every step happen live in the
studio dashboard.
"""

__version__ = "2.0.0"

from . import config, persona  # noqa: F401  (convenient re-exports)

__all__ = ["config", "persona", "__version__"]
