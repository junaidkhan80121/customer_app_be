from __future__ import annotations

import math


def page_meta(total: int, page: int, page_size: int) -> dict:
    pages = max(1, math.ceil(total / page_size)) if total else 0
    return {"total": total, "page": page, "page_size": page_size, "pages": pages}
