"""Per-run logging.

Each run truncates ``logs/latest.log`` and also writes a kept copy at
``projects/<project>/run.log``. Everything funnels through the ``k100dra``
logger — reporter activity, pipeline steps, and (most usefully) the **full**
ffmpeg stderr — so when a render fails you can see exactly why.
"""

from __future__ import annotations

import logging
import os

from . import config

_PKG = "k100dra"


def init_run_log(project: str) -> logging.Logger:
    """(Re)configure the package logger for a fresh run. Resets latest.log."""
    logger = logging.getLogger(_PKG)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:
            pass

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S")
    try:
        os.makedirs(config.LOG_DIR, exist_ok=True)
        latest = logging.FileHandler(config.LATEST_LOG, mode="w", encoding="utf-8")
        latest.setFormatter(fmt)
        logger.addHandler(latest)
    except Exception:
        pass
    try:
        kept = logging.FileHandler(os.path.join(config.project_dir(project), "run.log"),
                                   mode="w", encoding="utf-8")
        kept.setFormatter(fmt)
        logger.addHandler(kept)
    except Exception:
        pass

    logger.info("===== K100DRA run: %s =====", project)
    return logger


def get(name: str = "run") -> logging.Logger:
    return logging.getLogger(f"{_PKG}.{name}")
