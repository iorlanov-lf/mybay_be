from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Any, Union, Dict

from pydantic import BaseModel, Field, ConfigDict


# class MsgPayload(BaseModel):
#     msg_id: Optional[int]
#     msg_name: str

# class LocalizedAspect(BaseModel):
#     type: str
#     name: str
#     value: str


class MongoObjectId(BaseModel):
    """Wrapper for Mongo's ObjectId stored as {"$oid": "..."}."""

    model_config = ConfigDict(populate_by_name=True)

    oid: str = Field(..., alias="$oid")


class MongoDateTime(BaseModel):
    """Wrapper for Mongo date fields stored as {"$date": iso} ."""

    model_config = ConfigDict(populate_by_name=True)

    value: datetime = Field(..., alias="$date")


class Price(BaseModel):
    model_config = ConfigDict(extra="allow")

    value: Decimal
    currency: Optional[str] = None


class ImageAsset(BaseModel):
    model_config = ConfigDict(extra="allow")

    imageUrl: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None


class ReturnPeriod(BaseModel):
    value: Optional[int] = None
    unit: Optional[str] = None


class ReturnTerms(BaseModel):
    model_config = ConfigDict(extra="allow")

    returnsAccepted: Optional[bool] = None
    refundMethod: Optional[str] = None
    returnShippingCostPayer: Optional[str] = None
    returnPeriod: Optional[ReturnPeriod] = None


class ItemDetails(BaseModel):
    model_config = ConfigDict(extra="ignore")

    title: Optional[str] = None
    condition: Optional[str] = None
    conditionDescription: Optional[str] = None
    shortDescription: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Price] = None
    returnTerms: Optional[ReturnTerms] = None
    buyingOptions: Optional[List[str]] = None
    image: Optional[ImageAsset] = None
    itemWebUrl: Optional[str] = None

class VariantSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    release_year: Optional[str] = None
    model_name: Optional[str] = None
    model_description: Optional[str] = None
    model_id: Optional[str] = None
    model_number: Optional[str] = None
    screen_size: Optional[float] = None
    part_number: Optional[Union[str, List[str]]] = None
    color: Optional[Union[str, List[str]]] = None
    cpu_cores: Optional[int] = None
    cpu_model: Optional[str] = None
    cpu_speed: Optional[float] = None
    ssd_size: Optional[List[int]] = None
    ram_size: Optional[List[int]] = None


class VariantMatch(BaseModel):
    model_config = ConfigDict(extra="allow")

    variant: Optional[VariantSpec] = None
    distance: Optional[float] = None
    discrepancies: Optional[List[str]] = None


class DerivedData(BaseModel):
    model_config = ConfigDict(extra="allow")

    description: Optional[str] = None
    laptop_model: Optional[List[str]] = None
    model_number: Optional[List[str]] = None
    model_id: Optional[List[str]] = None
    part_number: Optional[List[str]] = None
    cpu_model: Optional[List[str]] = None
    cpu_family: Optional[List[str]] = None
    cpu_speed: Optional[List[float]] = None
    ssd_size: Optional[List[int]] = None
    screen_size: Optional[List[float]] = None
    ram_size: Optional[List[int]] = None
    release_year: Optional[List[str]] = None
    color: Optional[List[str]] = None
    specs_conflict: Optional[bool] = None
    variants: Optional[List[VariantMatch]] = None
    missing: Optional[List[str]] = None
    min_distance: Optional[float] = None
    specs_quality: Optional[str] = None


class LlmDerived(BaseModel):
    model_config = ConfigDict(extra="allow")

    charger: Optional[str] = None
    battery: Optional[str] = None
    screen: Optional[str] = None
    keyboard: Optional[str] = None
    housing: Optional[str] = None
    audio: Optional[str] = None
    ports: Optional[str] = None
    functionality: Optional[str] = None
    return_: Optional[str] = Field(default=None, alias="return")


class EbayItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    itemId: str
    details: ItemDetails
    inserted_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    processed_at: Optional[datetime] = None
    derived: Optional[DerivedData] = None
    llm_derived: Optional[LlmDerived] = None

class EbayItemsRequest(BaseModel):
    name: str
    skip: int = 0
    limit: int = 10
    filter: Optional[dict[str, Any]] = None
    
class FilterValue(BaseModel):
    value: Any
    count: int

class EbayItemsResponse(BaseModel):
    items: List[EbayItem]
    total_count: int
    available_filters: Optional[Dict[str, List[FilterValue]]] = None

class EbayFilterValuesRequest(BaseModel):
    name: str
    
class EbayFilterValuesResponse(BaseModel):
    available_filters: Optional[Dict[str, List[FilterValue]]] = None