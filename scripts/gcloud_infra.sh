# init (when you need to authenticate the very first time or switch accounts)
# this survives the terminal closure, so you only need to do it once per account
gcloud init

# get the project ID (ulaptop) to use in Docker image tagging and pushing
gcloud config get-value project
# get the project number (numeric value) to use in IAM permissions and other configurations
gcloud projects describe $(gcloud config get-value project) --format="value(projectNumber)"

# enable services (only need to do this once per project)
gcloud services enable compute.googleapis.com
gcloud services enable artifactregistry.googleapis.com
gcloud services enable run.googleapis.com
gcloud services enable secretmanager.googleapis.com

# set the region and artifact registry location (only need to do this once per project)
gcloud config set compute/region us-east4
gcloud config set artifacts/location us-east4

# create an artifact registry repository (only need to do this once per project)
gcloud artifacts repositories create ulaptop-repo \
    --repository-format=docker \
    --location=us-east4 \
    --description="Docker repository for ulaptop project"
# list repositories to verify creation
gcloud artifacts repositories list

# create a secret for the MongoDB connection string (only need to do this once per project)
echo -n "mongodb+srv://{user}:{password}@ulaptop.hlfbhab.mongodb.net" | \
gcloud secrets create MONGO_URI --data-file=-

# get the name of the service account
gcloud run services describe ulaptop-be --region us-east4 --format="value(spec.template.spec.serviceAccountName)"
# grant Cloud Run service account access to the secret (only need to do this once per project)
gcloud secrets add-iam-policy-binding MONGO_URI \
    --member="serviceAccount:{project_number}-compute@developer.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor"

# authenticate Docker to use gcloud as a credential helper (one time setup)
gcloud auth configure-docker us-east4-docker.pkg.dev

