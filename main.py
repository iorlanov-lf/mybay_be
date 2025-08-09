from fastapi import FastAPI, HTTPException
from models import MsgPayload, EbayResearchStatsRequest, EbayResearchStatsResponse
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
    
    count = len(doc.get("results", []))
    min_price = min(item['price_value'] for item in doc.get("results", [])) if doc.get("results") else 0
    max_price = max(item['price_value'] for item in doc.get("results", [])) if doc.get("results") else 0
    mean_price = sum(float(item['price_value']) for item in doc.get("results", [])) / count if count > 0 else 0
    median_price = sorted(float(item['price_value']) for item in doc.get("results", []))[(count - 1) // 2] if count > 0 else 0
    # Remove MongoDB's '_id' field if present, as Pydantic models don't expect it
    doc.pop("_id", None)
    
    
    return EbayResearchStatsResponse(count=count, min=min_price, max=max_price, mean=mean_price, median=median_price)


