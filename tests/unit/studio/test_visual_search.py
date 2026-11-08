from app.studio.visual_search import parse_candidates


def _page(idx: int, title: str, w: int, h: int, mime: str = "image/jpeg") -> dict[str, object]:
    return {
        "index": idx,
        "title": f"File:{title}",
        "imageinfo": [
            {
                "url": f"https://u/{title}",
                "thumburl": f"https://t/{title}",
                "width": w,
                "height": h,
                "mime": mime,
                "extmetadata": {
                    "LicenseShortName": {"value": "Public domain"},
                    "Artist": {"value": "<a href='x'>W. Röntgen</a>"},
                },
            }
        ],
    }


def test_parse_candidates_filters_and_orders() -> None:
    payload = {
        "query": {
            "pages": [
                _page(3, "hand.jpg", 1200, 900),
                _page(1, "small.jpg", 200, 150),
                _page(2, "Logo of X.png", 1200, 900, "image/png"),
                _page(4, "drawing.svg", 1200, 900, "image/svg+xml"),
                _page(0, "portrait.jpg", 800, 1000),
            ]
        }
    }
    cands = parse_candidates(payload)
    assert [c.title for c in cands] == ["portrait.jpg", "hand.jpg"]
    assert cands[0].attribution == "W. Röntgen — Public domain"
    assert cands[0].url == "https://t/portrait.jpg"
