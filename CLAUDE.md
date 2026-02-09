# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Virtual environment setup
python3 -m venv mybay_be_env
source mybay_be_env/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r dev-requirements.txt

# Run development server
uvicorn main:app --reload

# Run tests
pytest
pytest tests/test_main.py -v
```

## Architecture

This is a FastAPI backend serving eBay item data from MongoDB. It provides REST API endpoints for the mybay_fe frontend.

### Technology Stack
- **Framework**: FastAPI 0.116.1 with Uvicorn
- **Database**: MongoDB (localhost:27017, database: `mybaydb`)
- **Validation**: Pydantic 2.x
- **Testing**: Pytest with FastAPI TestClient

### Key Files
- `main.py` - All API endpoints and business logic
- `models.py` - Pydantic data models and schemas
- `tests/test_main.py` - Unit tests

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Health check |
| `/about` | GET | About page |
| `/ebay/items` | POST | Search/filter items with pagination and stats |
| `/ebay/filter_values` | POST | Get available filter values for a model |

### Data Models

**EbayItem** - Top-level item document:
- `itemId` - Unique eBay identifier
- `details` - eBay catalog data (title, price, condition, URL)
- `derived` - Regex-extracted specs (CPU, RAM, SSD, screen size, model info)
- `llmDerived` - AI-analyzed condition (screen, keyboard, battery, functionality)

### Filter System

Supports filtering on three field categories:
- **Derived fields**: `releaseYear`, `laptopModel`, `cpuModel`, `ssdSize`, `ramSize`, `screenSize`, `color`
- **LLM-derived fields**: `charger`, `battery`, `screen`, `keyboard`, `housing`, `functionality`, `componentListing`
- **Details fields**: `returnable`, `condition`

Filter logic supports variant matching with distance threshold and OR logic between direct matches and variants.

### MongoDB Collection
- Collection name matches model name (e.g., `mac_book_pro` for MacBookPro)
- Documents populated by mybay_jb data pipeline

## Code Standards

- CORS enabled for all origins (development)
- API documentation at `/docs` (Swagger) and `/redoc`
- Use Pydantic models for all request/response schemas
