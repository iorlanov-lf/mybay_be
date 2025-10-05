from typing import List, Optional, Any
from pydantic import BaseModel, Field


class MsgPayload(BaseModel):
    msg_id: Optional[int]
    msg_name: str

class LocalizedAspect(BaseModel):
    type: str
    name: str
    value: str

class EbayItem(BaseModel):
    itemId: str = Field(..., alias="﻿itemId")
    title: str
    model: str
    screen_size: str
    ram: str
    hdd: str
    red_flag: str
    price_value: str
    price_currency: str
    condition: str
    buyingOptions: str
    itemLocation_country: str
    match: str
    is_group: str
    needs_details: str
    itemWebUrl: str
    imageUrl: str
    localizedAspects: Any  # This is a JSON string, can be parsed to List[LocalizedAspect]

class EbayResearch(BaseModel):
    _id: str
    name: str
    results: List[EbayItem]

class EbayResearchStatsRequest(BaseModel):
    name: str
    params: Optional[dict] = None
    conditions: Optional[List[str]] = None
    
class EbayResearchStatsResponse(BaseModel):
    count: int
    min: float
    max: float  
    mean: float
    median: float

# Add request model for research-items
class EbayResearchItemsRequest(BaseModel):
    name: str
    skip: int = 0
    limit: int = 10
    params: Optional[dict] = None
    conditions: Optional[List[str]] = None

# MODEL

class EbayModelItem(BaseModel):
    itemId: Optional[str] = None
    title: Optional[str] = None
    condition: Optional[str] = None
    shortDescription: Optional[str] = None
    conditionDescription: Optional[str] = None
    description: Optional[str] = None
    itemWebUrl: Optional[str] = None
    imageUrl: Optional[str] = None
    is_laptop: Optional[bool] = None
    is_charger_included: Optional[str] = None # "Yes", "No", "Unknown"
    screen_damage: Optional[str] = None # "None", "Minor", "Major"
    battery_health: Optional[str] = None # "Good", "Fair", "Poor"
    keyboard_damage: Optional[str] = None # "None", "Minor", "Major"
    hosting_damage: Optional[str] = None # "None", "Minor", "Major"

class EbayModelItemsRequest(BaseModel):
    name: str
    skip: int = 0
    limit: int = 10
    include_all: bool = False
    
class EbayModelItemsResponse(BaseModel):
    items: List[EbayModelItem]
    total_count: int
    
# MODEL UPDATES
class EbayModelItemUpdateRequest(BaseModel):
    itemId: str
    is_laptop: Optional[bool] = None
    is_charger_included: Optional[str] = None # "Yes", "No", "Unknown"
    screen_damage: Optional[str] = None # "None", "Minor", "Major"
    battery_health: Optional[str] = None # "Good", "Fair", "Poor"
    keyboard_damage: Optional[str] = None # "None", "Minor", "Major"
    hosting_damage: Optional[str] = None # "None", "Minor", "Major"
    
class EbayModelItemUpdateResponse(BaseModel):
    success: bool
    message: Optional[str] = None