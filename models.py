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
    image: Optional[ImageAsset] = None
    itemWebUrl: Optional[str] = None

class VariantSpec(BaseModel):
    model_config = ConfigDict(extra="allow")

    releaseYear: Optional[str] = None
    modelName: Optional[str] = None
    modelDescription: Optional[str] = None
    modelId: Optional[str] = None
    modelNumber: Optional[str] = None
    screenSize: Optional[float] = None
    partNumber: Optional[Union[str, List[str]]] = None
    color: Optional[Union[str, List[str]]] = None
    cpuCores: Optional[int] = None
    cpuModel: Optional[str] = None
    cpuSpeed: Optional[float] = None
    ssdSize: Optional[List[int]] = None
    ramSize: Optional[List[int]] = None


class VariantMatch(BaseModel):
    model_config = ConfigDict(extra="allow")

    variant: Optional[VariantSpec] = None
    distance: Optional[float] = None
    discrepancies: Optional[List[str]] = None


class DerivedData(BaseModel):
    model_config = ConfigDict(extra="ignore")

    description: Optional[str] = None
    price: Optional[float] = None
    laptopModel: Optional[List[str]] = None
    modelNumber: Optional[List[str]] = None
    modelId: Optional[List[str]] = None
    partNumber: Optional[List[str]] = None
    cpuModel: Optional[List[str]] = None
    cpuFamily: Optional[List[str]] = None
    cpuSpeed: Optional[List[float]] = None
    ssdSize: Optional[List[int]] = None
    screenSize: Optional[List[float]] = None
    ramSize: Optional[List[int]] = None
    releaseYear: Optional[List[str]] = None
    color: Optional[List[str]] = None
    specsConflict: Optional[bool] = None
    variants: Optional[List[VariantMatch]] = None
    missing: Optional[List[str]] = None
    minDistance: Optional[float] = None
    specsQuality: Optional[str] = None


class LlmDerived(BaseModel):
    model_config = ConfigDict(extra="ignore")

    charger: Optional[str] = None
    battery: Optional[str] = None
    screen: Optional[str] = None
    keyboard: Optional[str] = None
    housing: Optional[str] = None
    audio: Optional[str] = None
    ports: Optional[str] = None
    functionality: Optional[str] = None
    componentListing: Optional[str] = None
    return_: Optional[str] = Field(default=None, alias="return")


class EbayItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    itemId: str
    details: ItemDetails
    insertedAt: Optional[datetime] = None
    updatedAt: Optional[datetime] = None
    processedAt: Optional[datetime] = None
    derived: Optional[DerivedData] = None
    llmDerived: Optional[LlmDerived] = None

class EbayItemsRequest(BaseModel):
    name: str
    skip: int = 0
    limit: int = 10
    filter: Optional[dict[str, Any]] = None
    sortSpecs: Optional[List[dict[str, Any]]] = None
    
class FilterValue(BaseModel):
    value: Any
    count: int

class Stats(BaseModel):
    min: Optional[float] = None
    max: Optional[float] = None
    median: Optional[float] = None
    mean: Optional[float] = None
    count: Optional[int] = None
    
class EbayItemsResponse(BaseModel):
    items: List[EbayItem]
    stats: Optional[Stats] = None
    availableFilters: Optional[Dict[str, List[FilterValue]]] = None

class EbayFilterValuesRequest(BaseModel):
    name: str
    
class EbayFilterValuesResponse(BaseModel):
    availableFilters: Optional[Dict[str, List[FilterValue]]] = None


class ErrorDetail(BaseModel):
    loc: Optional[List[Any]] = None
    msg: str
    type: str


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    details: Optional[List[ErrorDetail]] = None


class ErrorResponse(BaseModel):
    error: ErrorEnvelope