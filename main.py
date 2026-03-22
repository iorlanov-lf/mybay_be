import os
from contextlib import asynccontextmanager
from motor.motor_asyncio import AsyncIOMotorClient

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from models import EbayItemsByIdsRequest, EbayItemsByIdsResponse, ErrorDetail, ErrorEnvelope, ErrorResponse

#import mongo
from auth import router as auth_router, verify_session
from get_items import _build_epn_url
from util import _document_to_ebay_item

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. STARTUP: This runs inside the correct worker event loop!
    # Add readPreference=secondaryPreferred to offload your M10 Primary
    MONGODB_URL = os.getenv("MONGODB_URL", "mongodb://localhost:27017/")
    app.state.mongo_client = AsyncIOMotorClient(
        MONGODB_URL,
        maxPoolSize=50,       
        minPoolSize=5,        
        maxConnecting=2,      
        serverSelectionTimeoutMS=5000 
    )
    
    # Store the specific database reference
    app.state.db = app.state.mongo_client.get_database("mybaydb")
    
    # 2. YIELD: The app now accepts traffic from Locust/Users
    yield 
    
    # 3. SHUTDOWN: Cleanly close the connection pool when Cloud Run scales down
    app.state.mongo_client.close()
    
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://ulaptop.ai",
        "https://www.ulaptop.ai",
        "http://localhost:5173"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    details = [
        ErrorDetail(
            loc=list(err.get("loc", [])),
            msg=err.get("msg", ""),
            type=err.get("type", ""),
        )
        for err in exc.errors()
    ]
    body = ErrorResponse(
        error=ErrorEnvelope(
            code="VALIDATION_ERROR",
            message="Request validation failed",
            details=details,
        )
    )
    return JSONResponse(status_code=422, content=body.model_dump())


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    body = ErrorResponse(
        error=ErrorEnvelope(
            code=f"HTTP_{exc.status_code}",
            message=str(exc.detail),
        )
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump())


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    body = ErrorResponse(
        error=ErrorEnvelope(
            code="INTERNAL_ERROR",
            message=str(exc),
        )
    )
    return JSONResponse(status_code=500, content=body.model_dump())


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Hello"}


@app.get("/about")
def about() -> dict[str, str]:
    return {"message": "This is the about page."}


@app.get("/ebay/search-templates")
async def get_search_templates(request: Request, productName: str = Query(...), _: None = Depends(verify_session)):
    db = request.app.state.db
    docs = await db["search_templates"].find({"productName": productName}, {"_id": 0}).to_list(None)
    return docs


@app.post("/ebay/items/by-ids", response_model=EbayItemsByIdsResponse)
async def ebay_items_by_ids(request: Request, payload: EbayItemsByIdsRequest, _: None = Depends(verify_session)):
    db = request.app.state.db
    collection = None
    if payload.name == "MacBookPro":
        collection = db["mac_book_pro"]
    elif payload.name == "MacBookAir":
        collection = db["mac_book_air"]
    if collection is None:
        raise HTTPException(status_code=404, detail="Model collection not found")

    if not payload.itemIds:
        return EbayItemsByIdsResponse(items=[])

    docs = await collection.find({"itemId": {"$in": payload.itemIds}}).to_list(None)
    items = [_document_to_ebay_item(doc) for doc in docs]

    campaign_doc = await db["campaigns"].find_one({"name": payload.name})
    raw_id = campaign_doc.get("campaignId") if campaign_doc else None
    campaign_id = str(raw_id) if raw_id is not None else None
    if campaign_id:
        for item in items:
            if item.details and item.details.itemWebUrl:
                item.details.itemWebUrl = _build_epn_url(item.details.itemWebUrl, campaign_id)

    return EbayItemsByIdsResponse(items=items)


app.include_router(auth_router)

from get_items import router  # noqa: E402
app.include_router(router, dependencies=[Depends(verify_session)])
