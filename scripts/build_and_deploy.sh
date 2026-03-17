docker build -t mybay-be-mac .
docker build --platform linux/amd64 -t mybay-be .
docker tag mybay-be us-east4-docker.pkg.dev/ulaptop/ulaptop-repo/ulaptop-be
docker push us-east4-docker.pkg.dev/ulaptop/ulaptop-repo/ulaptop-be
gcloud run deploy ulaptop-be \
  --image us-east4-docker.pkg.dev/ulaptop/ulaptop-repo/ulaptop-be:latest \
  --region us-east4 \
  --set-secrets="MONGODB_URL=MONGO_URI:latest,\
TURNSTILE_SECRET_KEY=TURNSTILE_SECRET_KEY:latest,\
API_BYPASS_KEY=API_BYPASS_KEY:latest" \
  --allow-unauthenticated \
  --port 8080