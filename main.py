from fastapi import FastAPI, HTTPException, Query
from models import MsgPayload, \
        EbayResearchStatsRequest, EbayResearchStatsResponse, \
        EbayItem, EbayResearchItemsRequest, \
        EbayModelItemsRequest, EbayModelItemsResponse, EbayModelItem, \
        EbayModelItemUpdateRequest, EbayModelItemUpdateResponse
from pymongo import MongoClient
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
# Add CORS middleware to allow all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

messages_list: dict[int, MsgPayload] = {}

# MongoDB connection setup
client = MongoClient("mongodb://localhost:27017/")
db = client["mybaydb"]
researches_collection = db["researches"]



@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Hello"}


# About page route
@app.get("/about")
def about() -> dict[str, str]:
    return {"message": "This is the about page."}


# Route to add a message
@app.post("/messages/{msg_name}/")
def add_msg(msg_name: str) -> dict[str, MsgPayload]:
    # Generate an ID for the item based on the highest ID in the messages_list
    msg_id = max(messages_list.keys()) + 1 if messages_list else 0
    messages_list[msg_id] = MsgPayload(msg_id=msg_id, msg_name=msg_name)

    return {"message": messages_list[msg_id]}


# Route to list all messages
@app.get("/messages")
def message_items() -> dict[str, dict[int, MsgPayload]]:
    return {"messages:": messages_list}



@app.post("/ebay/research-stats", response_model=EbayResearchStatsResponse)
def ebay_research_stats(request: EbayResearchStatsRequest) -> EbayResearchStatsResponse:
    doc = researches_collection.find_one({"name": request.name})
    if not doc:
        raise HTTPException(status_code=404, detail="Research not found")
    
    if request.params:
        # Apply any additional filtering based on params if needed
        # This is a placeholder for future implementation
        if request.params.get("screen_size"):
            doc["results"] = [item for item in doc.get("results", []) if item.get("screen_size") == request.params["screen_size"]]  
        if request.params.get("ram"):
            doc["results"] = [item for item in doc.get("results", []) if item.get("ram") == request.params["ram"]]
        if request.params.get("ssd"):
            doc["results"] = [item for item in doc.get("results", []) if item.get("hdd") == request.params["ssd"]]  
        # Filter by conditions if provided
        if request.params.get("conditions"):
            doc["results"] = [item for item in doc.get("results", []) if item.get("condition") in request.params.get("conditions")]
        
    count = len(doc.get("results", []))
    # Treat price_value as number for calculations
    prices = [float(item['price_value']) for item in doc.get("results", [])]
    min_price = min(prices) if prices else 0
    max_price = max(prices) if prices else 0
    mean_price = sum(prices) / len(prices) if prices else 0
    median_price = sorted(prices)[(len(prices) - 1) // 2] if prices else 0
    
    return EbayResearchStatsResponse(count=count, min=min_price, max=max_price, mean=mean_price, median=median_price)



# New endpoint for paginated EbayItem list
@app.post("/ebay/research-items", response_model=list[EbayItem])
def ebay_research_items(request: EbayResearchItemsRequest):
    doc = researches_collection.find_one({"name": request.name})
    if not doc:
        raise HTTPException(status_code=404, detail="Research not found")
    
    if request.params:
        # Apply any additional filtering based on params if needed
        # This is a placeholder for future implementation
        if request.params.get("screen_size"):
            doc["results"] = [item for item in doc.get("results", []) if item.get("screen_size") == request.params["screen_size"]]  
        if request.params.get("ram"):
            doc["results"] = [item for item in doc.get("results", []) if item.get("ram") == request.params["ram"]]
        if request.params.get("ssd"):
            doc["results"] = [item for item in doc.get("results", []) if item.get("hdd") == request.params["ssd"]]  
        # Filter by conditions if provided
        if request.params.get("conditions"):
            doc["results"] = [item for item in doc.get("results", []) if item.get("condition") in request.params.get("conditions")]
        
    items = doc.get("results", [])
    # Sort items by price_value ascending
    items = sorted(items, key=lambda x: float(x.get("price_value", 0)))
    skip = max(request.skip, 0)
    limit = min(max(request.limit, 1), 100)
    paginated_items = items[skip:skip+limit]
    for item in paginated_items:
        item.pop("_id", None)
    return paginated_items


@app.post("/ebay/model-items", response_model=EbayModelItemsResponse)
def ebay_model_items(request: EbayModelItemsRequest):
    try:
        collection = None
        if request.name == "MacBookPro":
            collection = db["mac_book_pro"]
        if collection is None:
            raise HTTPException(status_code=404, detail="Model collection not found")
        all_items = []
        for doc in collection.find():
            if request.include_all:
                all_items.append(doc)
            else:
                if doc.get("is_laptop") in [None, True] and \
                    (not doc.get("is_charger_included") or \
                    not doc.get("screen_damage") or \
                    not doc.get("battery_health") or \
                    not doc.get("keyboard_damage") or \
                    not doc.get("hosting_damage")):
                        all_items.append(doc)
        # Sort items by price_value ascending
        all_items = sorted(all_items, key=lambda x: x.get("itemId"))
        skip = max(request.skip, 0)
        limit = min(max(request.limit, 1), 100)
        paginated_items = all_items[skip:skip+limit]
        ret_value = EbayModelItemsResponse(
            items=[],
            total_count=len(all_items)
        )
        for item in paginated_items:
            ebayModelItem = EbayModelItem(
                itemId=item.get("itemId"),
                title=item.get("title"),
                condition=item.get("condition", None),
                
                shortDescription=item.get("shortDescription", ""),
                conditionDescription=item.get("conditionDescription", ""),
                description=item.get("description", ""),
                itemWebUrl=item.get("itemWebUrl", ""),
                imageUrl=item.get("image").get("imageUrl") if item.get("image") else None,
                is_laptop=item.get("is_laptop", None),
                is_charger_included=item.get("is_charger_included", None),
                screen_damage=item.get("screen_damage", None),
                battery_health=item.get("battery_health", None),
                keyboard_damage=item.get("keyboard_damage", None),
                hosting_damage=item.get("hosting_damage", None)
            )
            ret_value.items.append(ebayModelItem)
            print(item.get("is_laptop"))

        return ret_value
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/ebay/update-model-item", response_model=EbayModelItemUpdateResponse)
def update_model_item(request: EbayModelItemUpdateRequest):
    try:
        # For now, we only support MacBookPro collection
        # This could be extended to support other models in the future
        collection = db["mac_book_pro"]
        
        # Find the item by itemId
        existing_item = collection.find_one({"itemId": request.itemId})
        if not existing_item:
            raise HTTPException(status_code=404, detail="Item not found")
        
        # Prepare update fields - only include fields that are not None
        update_fields = {}
        if request.is_laptop is not None:
            update_fields["is_laptop"] = request.is_laptop
        if request.is_charger_included is not None:
            update_fields["is_charger_included"] = request.is_charger_included
        if request.screen_damage is not None:
            update_fields["screen_damage"] = request.screen_damage
        if request.battery_health is not None:
            update_fields["battery_health"] = request.battery_health
        if request.keyboard_damage is not None:
            update_fields["keyboard_damage"] = request.keyboard_damage
        if request.hosting_damage is not None:
            update_fields["hosting_damage"] = request.hosting_damage
        
        # If no fields to update, return error
        if not update_fields:
            raise HTTPException(status_code=400, detail="No valid fields provided for update")
        
        # Update the item in MongoDB
        result = collection.update_one(
            {"itemId": request.itemId},
            {"$set": update_fields}
        )
        
        if result.modified_count == 0:
            return EbayModelItemUpdateResponse(
                success=False,
                message="No changes were made to the item"
            )
        
        return EbayModelItemUpdateResponse(
            success=True,
            message=f"Item {request.itemId} updated successfully"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



