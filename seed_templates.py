"""Seed the search_templates collection with Quick Start filter templates."""

from pymongo import MongoClient

client = MongoClient("mongodb://localhost:27017/")
db = client["mybaydb"]
collection = db["search_templates"]

TEMPLATES = [
    {
        "productName": "MacBook Pro",
        "templateName": "Budget under $500",
        "templateDescription": "Affordable options under $500",
        "filters": {"maxPrice": 500},
    },
    {
        "productName": "MacBook Pro",
        "templateName": "Developer Workhorse 32GB+",
        "templateDescription": "32GB+ RAM for development workloads",
        "filters": {"ram": "32"},
    },
    {
        "productName": "MacBook Pro",
        "templateName": "Recent 2022+ Models",
        "templateDescription": "Latest generation MacBook Pros",
        "filters": {"year": "2022"},
    },
    {
        "productName": "MacBook Pro",
        "templateName": "Best Condition",
        "templateDescription": "New and open box only",
        "filters": {
            "conditions": [
                {"value": "New", "code": "N"},
                {"value": "Open box", "code": "OB"},
            ],
        },
    },
    {
        "productName": "MacBookAir",
        "templateName": "Budget under $400",
        "templateDescription": "Affordable MacBook Air options under $400",
        "filters": {"maxPrice": 400},
    },
    {
        "productName": "MacBookAir",
        "templateName": "M-series Chip",
        "templateDescription": "Apple Silicon MacBook Air (M1, M2, M3, M4)",
        "filters": {"cpuFamily": ["M1", "M2", "M3", "M4"]},
    },
    {
        "productName": "MacBookAir",
        "templateName": "Recent (2022+)",
        "templateDescription": "MacBook Air models from 2022 onwards",
        "filters": {"releaseYear": [2022, 2023, 2024, 2025]},
    },
    {
        "productName": "MacBookAir",
        "templateName": "Best Condition",
        "templateDescription": "Listings with good specs completeness and consistency",
        "filters": {
            "specsCompleteness": ["Good"],
            "specsConsistency": ["Good"],
        },
    },
]

if __name__ == "__main__":
    collection.delete_many({})
    result = collection.insert_many(TEMPLATES)
    print(f"Inserted {len(result.inserted_ids)} search templates")
