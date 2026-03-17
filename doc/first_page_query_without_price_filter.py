second_page_query_without_price_filter = [
  {
    "$match": {
      "$and": [
        {
          "llmSpecs.productLine": {
            "$in": [
              "MacBook Pro"
            ]
          }
        },
        {
          "llmDerived.subject": {
            "$in": [
              "L"
            ]
          }
        },
        {
          "derived.price": {
            "$lt": 3000
          }
        }
      ]
    }
  },
  {
    "$facet": {
      "totalCount": [
        {
          "$count": "n"
        }
      ],
      "items": [
        {
          "$sort": {
            "derived.price": 1,
            "_id": 1
          }
        },
        {
          "$skip": 0
        },
        {
          "$limit": 10
        }
      ],
      "stats": [
        {
          "$group": {
            "_id": null,
            "min": {
              "$min": "$derived.price"
            },
            "max": {
              "$max": "$derived.price"
            },
            "mean": {
              "$avg": "$derived.price"
            },
            "median": {
              "$median": {
                "input": "$derived.price",
                "method": "approximate"
              }
            },
            "count": {
              "$sum": 1
            }
          }
        }
      ],
      "priceBins": [
        {
          "$bucket": {
            "groupBy": "$derived.price",
            "boundaries": [
              0,
              100,
              200,
              300,
              400,
              500,
              600,
              700,
              800,
              900,
              1000,
              1100,
              1200,
              1300,
              1400,
              1500,
              1600,
              1700,
              1800,
              1900,
              2000,
              2100,
              2200,
              2300,
              2400,
              2500,
              2600,
              2700,
              2800,
              2900,
              3000
            ],
            "default": "3000+",
            "output": {
              "count": {
                "$sum": 1
              }
            }
          }
        }
      ],
      "releaseYear": [
        {
          "$addFields": {
            "_combined": {
              "$setUnion": [
                {
                  "$ifNull": [
                    "$llmSpecs.releaseYear",
                    []
                  ]
                },
                {
                  "$ifNull": [
                    "$llmAnalysis.specsAnalysis.releaseYear.bestGuess",
                    []
                  ]
                }
              ]
            }
          }
        },
        {
          "$unwind": "$_combined"
        },
        {
          "$group": {
            "_id": "$_combined",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "cpuFamily": [
        {
          "$addFields": {
            "_combined": {
              "$setUnion": [
                {
                  "$ifNull": [
                    "$llmSpecs.cpuFamily",
                    []
                  ]
                },
                {
                  "$ifNull": [
                    "$llmAnalysis.specsAnalysis.cpuFamily.bestGuess",
                    []
                  ]
                }
              ]
            }
          }
        },
        {
          "$unwind": "$_combined"
        },
        {
          "$group": {
            "_id": "$_combined",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "screenSize": [
        {
          "$addFields": {
            "_combined": {
              "$setUnion": [
                {
                  "$ifNull": [
                    "$llmSpecs.screenSize",
                    []
                  ]
                },
                {
                  "$ifNull": [
                    "$llmAnalysis.specsAnalysis.screenSize.bestGuess",
                    []
                  ]
                }
              ]
            }
          }
        },
        {
          "$unwind": "$_combined"
        },
        {
          "$group": {
            "_id": "$_combined",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "ramSize": [
        {
          "$addFields": {
            "_combined": {
              "$setUnion": [
                {
                  "$ifNull": [
                    "$llmSpecs.ramSize",
                    []
                  ]
                },
                {
                  "$ifNull": [
                    "$llmAnalysis.specsAnalysis.ramSize.bestGuess",
                    []
                  ]
                }
              ]
            }
          }
        },
        {
          "$unwind": "$_combined"
        },
        {
          "$group": {
            "_id": "$_combined",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "ssdSize": [
        {
          "$addFields": {
            "_combined": {
              "$setUnion": [
                {
                  "$ifNull": [
                    "$llmSpecs.ssdSize",
                    []
                  ]
                },
                {
                  "$ifNull": [
                    "$llmAnalysis.specsAnalysis.ssdSize.bestGuess",
                    []
                  ]
                }
              ]
            }
          }
        },
        {
          "$unwind": "$_combined"
        },
        {
          "$group": {
            "_id": "$_combined",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "productLine": [
        {
          "$unwind": "$llmSpecs.productLine"
        },
        {
          "$group": {
            "_id": "$llmSpecs.productLine",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "cpuModel": [
        {
          "$unwind": "$llmSpecs.cpuModel"
        },
        {
          "$group": {
            "_id": "$llmSpecs.cpuModel",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "cpuSpeed": [
        {
          "$unwind": "$llmSpecs.cpuSpeed"
        },
        {
          "$group": {
            "_id": "$llmSpecs.cpuSpeed",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "color": [
        {
          "$unwind": "$llmSpecs.color"
        },
        {
          "$group": {
            "_id": "$llmSpecs.color",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "modelNumber": [
        {
          "$unwind": "$llmSpecs.modelNumber"
        },
        {
          "$group": {
            "_id": "$llmSpecs.modelNumber",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "modelId": [
        {
          "$unwind": "$llmSpecs.modelId"
        },
        {
          "$group": {
            "_id": "$llmSpecs.modelId",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "partNumber": [
        {
          "$unwind": "$llmSpecs.partNumber"
        },
        {
          "$group": {
            "_id": "$llmSpecs.partNumber",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "specsCompleteness": [
        {
          "$group": {
            "_id": "$llmAnalysis.specsCompleteness",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "specsConsistency": [
        {
          "$group": {
            "_id": "$llmAnalysis.specsConsistency",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "charger": [
        {
          "$group": {
            "_id": "$llmDerived.charger",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "battery": [
        {
          "$group": {
            "_id": "$llmDerived.battery",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "screen": [
        {
          "$group": {
            "_id": "$llmDerived.screen",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "keyboard": [
        {
          "$group": {
            "_id": "$llmDerived.keyboard",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "housing": [
        {
          "$group": {
            "_id": "$llmDerived.housing",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "audio": [
        {
          "$group": {
            "_id": "$llmDerived.audio",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "ports": [
        {
          "$group": {
            "_id": "$llmDerived.ports",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "functionality": [
        {
          "$group": {
            "_id": "$llmDerived.functionality",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "componentListing": [
        {
          "$group": {
            "_id": "$llmDerived.componentListing",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "subject": [
        {
          "$group": {
            "_id": "$llmDerived.subject",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "returnable": [
        {
          "$group": {
            "_id": "$details.returnTerms.returnsAccepted",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "returnShippingCostPayer": [
        {
          "$group": {
            "_id": "$details.returnTerms.returnShippingCostPayer",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ],
      "condition": [
        {
          "$group": {
            "_id": "$details.condition",
            "count": {
              "$sum": 1
            }
          }
        },
        {
          "$sort": {
            "_id": 1
          }
        }
      ]
    }
  }
]