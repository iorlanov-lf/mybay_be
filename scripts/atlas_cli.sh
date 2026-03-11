# login to atlas
atlas auth login

# list projects to get the project ID
atlas projects list

# create an access list entry for the current IP address (valid for 24 hours)
atlas accessLists create --currentIp --deleteAfter $(date -v+24H +"%Y-%m-%dT%H:%M:%S%z") --comment "Home Laptop 24h"