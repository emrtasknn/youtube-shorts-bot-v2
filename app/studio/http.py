"""Shared HTTP identity for Studio.

Wikimedia rejects automated requests without a descriptive User-Agent that
names the tool and a way to contact its owner (https://w.wiki/4wJS); requests
from cloud runners such as GitHub Actions are refused outright. Every Studio
request to a public site uses this one header.
"""

from __future__ import annotations

import httpx

USER_AGENT = (
    "BirGaripTarihStudio/1.0 "
    "(https://github.com/emrtasknn/youtube-shorts-bot-v2) "
    f"httpx/{httpx.__version__}"
)
