"""Fill the end card and description credits of film.json from credits.json.

    python docs/longform/vecihi-hurkus/build_credits.py

credits.json maps an image key to its Commons file, licence and author (written
while downloading). Only images the film actually uses are credited.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> None:
    credits = json.loads((HERE / "credits.json").read_text(encoding="utf-8"))
    film = json.loads((HERE / "film.json").read_text(encoding="utf-8"))
    used = {Path(sc[k]).stem for sc in film["scenes"] for k in ("image", "image2") if sc.get(k)}
    card, desc = [], []
    for key, c in sorted(credits.items(), key=lambda kv: kv[1]["file"].lower()):
        if key not in used:
            continue
        lic = c["license"] or "?"
        who = c["artist"].replace("\n", " ").strip()
        free = lic.lower().startswith(("public domain", "pd", "no restrictions", "cc0"))
        card.append(f"{c['file']} · {lic}" + ("" if free or not who else f" · {who[:50]}"))
        desc.append(
            f"- {c['file']} — {lic}" + (f" — {who}" if who and not free else "") + f" — {c['page']}"
        )
    for sc in film["scenes"]:
        if sc["kind"] == "end":
            sc["lines"] = ["Wikimedia Commons", *card]
    (HERE / "film.json").write_text(
        json.dumps(film, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    (HERE / "credits_description.json").write_text(
        json.dumps(desc, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    missing = sorted(used - set(credits))
    print(f"{len(card)} görsel kredilendi" + (f"; kredisi eksik: {missing}" if missing else ""))


if __name__ == "__main__":
    main()
