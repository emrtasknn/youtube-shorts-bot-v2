import pytest

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


def test_search_terms_use_names_not_whole_sentences() -> None:
    from app.studio.visual_search import search_terms

    assert search_terms("Naaşı önce İstanbul'dan Yavuz zırhlısıyla İzmit'e taşındı.")[0] == (
        "İstanbul Yavuz İzmit"
    )
    assert (
        search_terms("Dolmabahçe Sarayı'ndaki o odada saat hâlâ dokuzu beş geçeyi gösteriyor.")[0]
        == "Dolmabahçe Sarayı"
    )
    assert search_terms("21 Kasım 1938'de Etnografya Müzesi'ndeki geçici kabrine konuldu.")[0] == (
        "Kasım 1938 Etnografya Müzesi"
    )
    assert search_terms("Anıtkabir") == ["Anıtkabir"]
    assert search_terms("Wilhelm Röntgen portrait")[0] == "Wilhelm Röntgen portrait"


@pytest.mark.asyncio
async def test_search_commons_terms_tries_until_found(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.studio import visual_search
    from app.studio.models import Candidate

    tried: list[str] = []

    async def fake(query: str, *, limit: int = 3, timeout: float = 30.0) -> list[Candidate]:
        tried.append(query)
        return [Candidate("u", "t", "x")] if query == "B" else []

    monkeypatch.setattr(visual_search, "search_commons", fake)
    assert len(await visual_search.search_commons_terms(["A", "B", "C"])) == 1
    assert tried == ["A", "B"]


def test_image_url_turns_commons_page_into_file() -> None:
    from app.studio.visual_search import image_url

    assert image_url("https://commons.wikimedia.org/wiki/File:Anitkabir.jpg") == (
        "https://commons.wikimedia.org/wiki/Special:FilePath/Anitkabir.jpg"
    )
    assert image_url(" https://example.com/a.jpg ") == "https://example.com/a.jpg"
