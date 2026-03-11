second_page_query_with_price_filter = [
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
            'stats': [
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
            'releaseYearOptions': [
                {
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