second_page_query_with_price_filter = [
    {
        '$match': {
            'llmSpecs.productLine': 'MacBook Pro', 
            'llmDerived.subject': 'L', 
            'derived.price': {
                '$lt': 3000
            }, 
            'derived.price': {
                '$gte': 500, 
                '$lte': 1500
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
            'items': [
                {
                    '$sort': {
                        'derived.price': 1, 
                        '_id': 1
                    }
                }, {
                    '$skip': 10
                }, {
                    '$limit': 10
                }
            ]
        }
    }
]