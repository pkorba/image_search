from dataclasses import dataclass


@dataclass
class ImageData:
    url: str
    width: int
    height: int
    engine: str
