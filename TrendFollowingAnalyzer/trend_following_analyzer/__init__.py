from .config import load_config


def screen_date(*args, **kwargs):
    # Lazy import keeps indicator/regime modules independently testable.
    from .screen import screen_date as _screen_date

    return _screen_date(*args, **kwargs)


__all__ = ["load_config", "screen_date"]
