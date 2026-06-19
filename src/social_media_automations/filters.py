from __future__ import annotations

import re
from typing import Callable, Optional


def make_text_filter(text: Optional[str], regex: Optional[str]) -> Callable[[str], bool]:
    if text is not None and regex is not None:
        raise ValueError("pass either text= or regex=, not both")
    if text is not None:
        needle = text.lower()
        return lambda s: needle in (s or "").lower()
    if regex is not None:
        pattern = re.compile(regex)
        return lambda s: pattern.search(s or "") is not None
    return lambda s: True
