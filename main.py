from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from models import EbayItemsByIdsRequest, EbayItemsByIdsResponse, ErrorDetail, ErrorEnvelope, ErrorResponse

import mongo
from auth import router as auth_router, verify_session
from util import _document_to_ebay_item

app = FastAPI()
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
async def get_search_templates(productName: str = Query(...), _: None = Depends(verify_session)):
    docs = await mongo.db["search_templates"].find({"productName": productName}, {"_id": 0}).to_list(None)
    return docs


@app.post("/ebay/items/by-ids", response_model=EbayItemsByIdsResponse)
async def ebay_items_by_ids(request: EbayItemsByIdsRequest, _: None = Depends(verify_session)):
    collection = None
    if request.name == "MacBookPro":
        collection = mongo.db["mac_book_pro"]
    elif request.name == "MacBookAir":
        collection = mongo.db["mac_book_air"]
    if collection is None:
        raise HTTPException(status_code=404, detail="Model collection not found")

    if not request.itemIds:
        return EbayItemsByIdsResponse(items=[])

    docs = await collection.find({"itemId": {"$in": request.itemIds}}).to_list(None)
    items = [_document_to_ebay_item(doc) for doc in docs]
    return EbayItemsByIdsResponse(items=items)


app.include_router(auth_router)

from get_items import router  # noqa: E402
app.include_router(router, dependencies=[Depends(verify_session)])
