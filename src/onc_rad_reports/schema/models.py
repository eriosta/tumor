# Placeholder for schema helpers (RadLex/SNOMED mapping, enums, validators)
from pydantic import BaseModel, field_validator
from typing import Optional, Literal

class PrimaryTumor(BaseModel):
    size_mm: Optional[int]
    location: Optional[str]
    margin: Optional[Literal["regular","irregular","spiculated"]]
    enhancement: Optional[Literal["none","hypo","iso","hyper"]]
    certainty: Optional[Literal["possible","probable","definite"]]

# Add LymphNode, Metastasis, Relations...
