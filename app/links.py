import re
from dataclasses import dataclass

from linkify_it import LinkifyIt
from pydantic import HttpUrl, TypeAdapter


LINKIFY = LinkifyIt()
HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
JOINED_URLS = re.compile(r"(?<=[,;|!?()\[\]{}])(?=https?://)", re.IGNORECASE)
EMPTY_URL = re.compile(r"https?://(?=$|[\s<>\"'])", re.IGNORECASE)


@dataclass(frozen=True)
class CtaLink:
    url: str
    start: int
    end: int


def extract_cta_link(message: str) -> CtaLink:
    if EMPTY_URL.search(message):
        raise ValueError("CTA link must be a valid HTTP or HTTPS URL")

    boundaries = [0, *(match.start() for match in JOINED_URLS.finditer(message)), len(message)]
    links = []
    for start, end in zip(boundaries, boundaries[1:]):
        for match in LINKIFY.match(message[start:end]) or []:
            if match.schema != "mailto:":
                links.append((match, start))

    if len(links) != 1:
        raise ValueError("message must contain exactly one CTA link")

    match, offset = links[0]
    if match.schema.lower() not in {"http:", "https:"}:
        raise ValueError("CTA link must be a valid HTTP or HTTPS URL")
    try:
        HTTP_URL_ADAPTER.validate_python(match.raw)
    except ValueError as error:
        raise ValueError("CTA link must be a valid HTTP or HTTPS URL") from error
    return CtaLink(match.raw, offset + match.index, offset + match.last_index)
