first_page_query_with_price_filter = [
    {
        '$match': {
            'llmSpecs.productLine': 'MacBook Pro', 
            'llmDerived.subject': 'L', 
            'derived.price': {
                '$lt': 3000
            }, 
            '$or': [
                {
                    'llmSpecs.ramSize': {
                        '$in': [
                            16
                        ]
                    }
                }, {
                    'llmAnalysis.specsAnalysis.ramSize.bestGuess': {
                        '$in': [
                            16
                        ]
                    }
                }
            ], 
            'llmDerived.screen': {
                '$in': [
                    'G', 'NM', 'MN'
                ]
            }
        }
    }, {
        '$facet': {
            'baseStats': [
                {
                    '$group': {
                        '_id': None, 
                        'median': {
                            '$median': {
                                'input': '$derived.price', 
                                'method': 'approximate'
                            }
                        }, 
                        'min': {
                            '$min': '$derived.price'
                        }, 
                        'max': {
                            '$max': '$derived.price'
                        }, 
                        'mean': {
                            '$avg': '$derived.price'
                        }, 
                        'count': {
                            '$sum': 1
                        }
                    }
                }
            ], 
            'basePriceBins': [
                {
                    '$bucket': {
                        'groupBy': '$derived.price', 
                        'boundaries': [
                            0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100, 2200, 2300, 2400, 2500, 2600, 2700, 2800, 2900, 3000
                        ], 
                        'default': '3000+', 
                        'output': {
                            'count': {
                                '$sum': 1
                            }
                        }
                    }
                }
            ], 
            'priceBins': [
                {
                    '$match': {
                        'derived.price': {
                            '$gte': 500, 
                            '$lte': 1500
                        }
                    }
                }, {
                    '$bucket': {
                        'groupBy': '$derived.price', 
                        'boundaries': [
                            0, 100, 200, 300, 400, 500, 600, 700, 800, 900, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 1800, 1900, 2000, 2100, 2200, 2300, 2400, 2500, 2600, 2700, 2800, 2900, 3000
                        ], 
                        'default': '3000+', 
                        'output': {
                            'count': {
                                '$sum': 1
                            }
                        }
                    }
                }
            ], 
            'releaseYearOptions': [
                {
                    '$match': {
                        'derived.price': {
                            '$gte': 500, 
                            '$lte': 1500
                        }
                    }
                }, {
                    '$addFields': {
                        'combinedReleaseYears': {
                            '$setUnion': [
                                {
                                    '$ifNull': [
                                        '$llmSpecs.releaseYear', []
                                    ]
                                }, {
                                    '$ifNull': [
                                        '$llmAnalysis.specsAnalysis.releaseYear.bestGuess', []
                                    ]
                                }
                            ]
                        }
                    }
                }, {
                    '$unwind': '$combinedReleaseYears'
                }, {
                    '$group': {
                        '_id': '$combinedReleaseYears', 
                        'count': {
                            '$sum': 1
                        }
                    }
                }, {
                    '$sort': {
                        '_id': 1
                    }
                }
            ], 
            'items': [
                {
                    '$match': {
                        'derived.price': {
                            '$gte': 500, 
                            '$lte': 1500
                        }
                    }
                }, {
                    '$sort': {
                        'derived.price': 1, 
                        '_id': 1
                    }
                }, {
                    '$skip': 0
                }, {
                    '$limit': 10
                }
            ]
        }
    }
]