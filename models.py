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
    localizedAspects: Any  # This is a JSON string, can be parsed to List[LocalizedAspect]

class EbayResearch(BaseModel):
    _id: str
    name: str
    results: List[EbayItem]
    
class EbayResearchStatsRequest(BaseModel):
    name: str
        
    
class EbayResearchStatsResponse(BaseModel):
    count: int
    min: float
    max: float  
    mean: float
    median: float
    