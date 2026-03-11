# authenticate (every time you start a new terminal session)
gcloud init

# deploy the image to Cloud Run (you need to do this every time you want to update the deployed service)
gcloud run deploy ulaptop-be \
  --image us-east4-docker.pkg.dev/ulaptop/ulaptop-repo/ulaptop-be:latest \
  --region us-east4 \
  --set-secrets="MONGODB_URL=MONGO_URI:latest" \
  --allow-unauthenticated \
  --port 8080


# view log in terminal
gcloud alpha run services logs tail ulaptop-be --project ulaptop