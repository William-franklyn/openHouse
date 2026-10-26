"""Built-in Room DJ tracks, so a mod can play music without needing to
upload their own file. Nobody has a downloaded mp3 sitting around anymore -
this closes that gap with a curated, always-available catalog.

All 20 tracks are by Kevin MacLeod (incompetech.com), mirrored on the
Internet Archive (https://archive.org/details/Incompetech), licensed
CC BY 3.0 - free to use, attribution required. That's why `artist` and
`license` ride along with every track sent to clients: the now-playing
bar shows them, which is what satisfies the attribution requirement.

Every filename below was verified against the Archive's own metadata API
(https://archive.org/metadata/Incompetech) before being hard-coded here -
not guessed.
"""

from urllib.parse import quote

_BASE_URL = "https://archive.org/download/Incompetech/mp3-royaltyfree/"
_ARTIST = "Kevin MacLeod (incompetech.com)"
_LICENSE = "CC BY 3.0"
_LICENSE_URL = "https://creativecommons.org/licenses/by/3.0/"

_TITLES = [
    "Airport Lounge",
    "AcidJazz",
    "Air Prelude",
    "Achaidh Cheide",
    "Atlantean Twilight",
    "Autumn Day",
    "Avec Soin",
    "Bathed in the Light",
    "Beach Bum",
    "Beach Party",
    "Beachfront Celebration",
    "Americana",
    "Ambler",
    "At The Shore",
    "Birch Run",
    "Backed Vibes Clean",
    "Bass Vibes",
    "Angevin",
    "Aces High",
    "Arcadia",
]


def _slug(title: str) -> str:
    return title.lower().replace(" ", "-")


LIBRARY_TRACKS = [
    {
        "id": _slug(title),
        "title": title,
        "artist": _ARTIST,
        "license": _LICENSE,
        "license_url": _LICENSE_URL,
        "url": _BASE_URL + quote(f"{title}.mp3"),
    }
    for title in _TITLES
]

_BY_ID = {t["id"]: t for t in LIBRARY_TRACKS}


def get_track(track_id: str) -> dict | None:
    return _BY_ID.get(track_id)


def list_tracks() -> list[dict]:
    return LIBRARY_TRACKS
