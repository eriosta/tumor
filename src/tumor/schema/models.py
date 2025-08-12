from pydantic import BaseModel
from typing import Optional, Literal, List

class LymphNode(BaseModel):
    region: Optional[Literal["thoracic","abdominal","pelvic"]]
    station: Optional[str]
    short_axis_mm: Optional[int]
    necrosis: Optional[bool]

class Metastasis(BaseModel):
    site: Optional[Literal["liver","adrenal","bone","lung","peritoneum"]]
    size_mm: Optional[int]

class PrimaryTumor(BaseModel):
    organ: Optional[Literal["lung","colon","pancreas","kidney","liver","ovary","prostate","stomach"]]
    location: Optional[str]
    size_mm: Optional[int]
    margin: Optional[Literal["regular","irregular","spiculated"]]
    enhancement: Optional[Literal["hypo","iso","hyper"]]
    certainty: Optional[Literal["possible","probable","definite"]]
