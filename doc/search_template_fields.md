# Search Template Filter Fields Reference

Templates are stored in the `search_templates` MongoDB collection and seeded via `seed_templates.py`.
The frontend reads them at `GET /ebay/search-templates?productName=<name>` and applies them
as filter state in `AppleLaptop.tsx`.

## Top-Level Template Document

```json
{
  "productName": "MacBookPro",
  "templateName": "My Template",
  "templateDescription": "Short description shown in the popover",
  "filters": { ... }
}
```

`productName` must exactly match the `laptopModel` value used by the frontend:
`"MacBookPro"` or `"MacBookAir"`.

---

## `filters` Field Reference

### Single-value fields (string)

Omit the field (or set to the "all" sentinel) to leave that filter unset.

| Field | API filter | "All" sentinel | Notes |
|---|---|---|---|
| `year` | `releaseYear` | `"All years"` | Year string, e.g. `"2022"` |
| `ram` | `ramSize` | `"All sizes"` | GB as string: `"8"`, `"16"`, `"32"`, `"64"` |
| `ssd` | `ssdSize` | `"All sizes"` | GB as string: `"256"`, `"512"`, `"1000"`, `"2000"` |
| `screen` | `screenSize` | `"All sizes"` | Inches as string: `"13"`, `"14"`, `"15"`, `"16"` |
| `cpuFamily` | `cpuFamily` | `"All CPU families"` | Dynamic from data, e.g. `"M1"`, `"M2 Pro"` |
| `cpuModel` | `cpuModel` | `"All CPU models"` | Dynamic from data |
| `cpuSpeed` | `cpuSpeed` | `"All CPU speeds"` | GHz as string, e.g. `"3.0"` |
| `modelNumber` | `modelNumber` | `"All model numbers"` | Dynamic from data, e.g. `"MacBookPro18,1"` |
| `modelId` | `modelId` | `"All model ids"` | Dynamic from data, e.g. `"MLX43LL/A"` |
| `partNumber` | `partNumber` | `"All part numbers"` | Dynamic from data, e.g. `"A2141"` |
| `color` | `color` | `"All colors"` | Dynamic from data, e.g. `"Space Gray"` |

Dynamic fields — valid values depend on what's in the database. Omit them in templates
unless you know the exact string the pipeline stores.

### Numeric range fields

Omit to leave unbounded.

| Field | API filter | Type |
|---|---|---|
| `minPrice` | `minPrice` | `number` (USD) |
| `maxPrice` | `maxPrice` | `number` (USD) |

### Multi-select fields (array of `{ value, code }`)

Empty array or omitting the field means "no filter on this dimension".

Each item must have at minimum `"value"` and `"code"` (code drives the badge display in the UI).

---

#### `conditions` → API `condition`

| `value` | `code` | Meaning |
|---|---|---|
| `"New"` | `"N"` | New |
| `"Open box"` | `"OB"` | Open box |
| `"Excellent - Refurbished"` | `"ER"` | Excellent refurbished |
| `"Very Good - Refurbished"` | `"VGR"` | Very good refurbished |
| `"Good - Refurbished"` | `"GR"` | Good refurbished |
| `"Used"` | `"U"` | Used |
| `"For parts or not working"` | `"FP"` | Parts / not working |

---

#### `batteries` → API `battery`

| `value` | `code` | Meaning |
|---|---|---|
| `"G"` | `"G"` | Good |
| `"F"` | `"F"` | Fair |
| `"P"` | `"P"` | Poor |
| `"NM"` | `"NM"` | Not mentioned |
| `"N"` | `"N"` | Not included |
| `"U"` | `"U"` | Unknown (legacy) |

---

#### `screenConditions` / `keyboardConditions` / `housingConditions` / `audioConditions` / `portsConditions`
→ API `screen` / `keyboard` / `housing` / `audio` / `ports`

All five use the same grade set:

| `value` | `code` | Meaning |
|---|---|---|
| `"G"` | `"G"` | Good |
| `"NM"` | `"NM"` | Not mentioned |
| `"MN"` | `"MN"` | Minor damage |
| `"MJ"` | `"MJ"` | Major damage |

---

#### `functionalities` → API `functionality`

| `value` | `code` | Meaning |
|---|---|---|
| `"L"` | `"L"` | Full laptop |
| `"D"` | `"D"` | Desktop only (lid broken) |
| `"NF"` | `"NF"` | Not functional |
| `"NM"` | `"NM"` | Not mentioned |
| `"U"` | `"U"` | Unknown (legacy) |

---

#### `chargers` → API `charger`

| `value` | `code` | Meaning |
|---|---|---|
| `"Y"` | `"Y"` | Included |
| `"N"` | `"N"` | Not included |
| `"NM"` | `"NM"` | Not mentioned |
| `"U"` | `"U"` | Unknown (legacy) |

---

#### `specsCompleteness` → API `specsCompleteness`

| `value` | `code` | Meaning |
|---|---|---|
| `"Good"` | `"Good"` | All main specs present |
| `"Fair"` | `"Fair"` | Some specs missing |
| `"Bad"` | `"Bad"` | Most specs missing |

---

#### `specsConsistency` → API `specsConsistency`

| `value` | `code` | Meaning |
|---|---|---|
| `"Good"` | `"Good"` | No conflicts |
| `"Bad"` | `"Bad"` | Conflicting specs found |

---

#### `returnables` → API `returnable`

| `value` | `code` | Meaning |
|---|---|---|
| `"true"` | `"true"` | Returns accepted |
| `"false"` | `"false"` | No returns |

Note: stored as strings, converted to booleans when building the API request.

---

#### `returnShippingPayers` → API `returnShippingCostPayer`

| `value` | `code` | Meaning |
|---|---|---|
| `"SELLER"` | `"SELLER"` | Seller pays return shipping |
| `"BUYER"` | `"BUYER"` | Buyer pays return shipping |

---

## Complete Example

```json
{
  "productName": "MacBookPro",
  "templateName": "Best Value 16GB",
  "templateDescription": "Good-condition 16GB models under $800",
  "filters": {
    "ram": "16",
    "maxPrice": 800,
    "conditions": [
      { "value": "Used", "code": "U" },
      { "value": "Good - Refurbished", "code": "GR" },
      { "value": "Excellent - Refurbished", "code": "ER" }
    ],
    "functionalities": [
      { "value": "L", "code": "L" }
    ],
    "specsCompleteness": [
      { "value": "Good", "code": "Good" }
    ]
  }
}
```

---

## Known Issue in seed_templates.py

The MacBook Air "M-series Chip" and "Recent (2022+)" templates use arrays for `cpuFamily`
and `releaseYear`. These fields are **single-value** in the frontend — only the first element
would be used, and the filter label would be wrong. Use the correct single-string or `year`
field instead:

```json
{ "year": "2022" }
```
