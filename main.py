from fastapi import FastAPI, HTTPException, Query
from models import MsgPayload, EbayResearchStatsRequest, EbayResearchStatsResponse, EbayItem, EbayResearchItemsRequest
from pymongo import MongoClient
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
    
    items = doc.get("results", [])
    # Sort items by price_value ascending
    items = sorted(items, key=lambda x: float(x.get("price_value", 0)))
    skip = max(request.skip, 0)
    limit = min(max(request.limit, 1), 100)
    paginated_items = items[skip:skip+limit]
    for item in paginated_items:
        item.pop("_id", None)
    return paginated_items


