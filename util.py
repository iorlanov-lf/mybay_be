from typing import Any
from pydantic import ValidationError

from fastapi import HTTPException
from models import EbayItem


def _document_to_ebay_item(doc: dict[str, Any]) -> EbayItem:
    model_fields = getattr(EbayItem, "model_fields", None)
    allowed_fields = set(model_fields.keys()) if model_fields else set(getattr(EbayItem, "__fields__", {}).keys())
    payload = doc if not allowed_fields else {k: v for k, v in doc.items() if k in allowed_fields}

    try:
        ebay_item = EbayItem.model_validate(payload)
    except ValidationError as e:
        error_details = e.errors()
        missing_fields = []
        for error in error_details:
            if error['type'] == 'value_error.missing' or error['msg'] == 'Field required':
                missing_fields.append(error['loc'][-1])
        print(f"Missing fields: {missing_fields}")
        raise HTTPException(status_code=400, detail=str(e))
    return ebay_item
