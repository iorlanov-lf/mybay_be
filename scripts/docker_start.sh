# local startup script for testing the API with a local MongoDB instance running on the host machine
docker run -p 8000:8080 \
  -e MONGODB_URL="mongodb://host.docker.internal:27017/" \
  --name mybay-api-test \
  mybay-be-mac