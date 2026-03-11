# to run on MacOS
docker build -t mybay-be-mac .

# to run in GCP
docker build --platform linux/amd64 -t mybay-be .

# tag the Docker image with the Artifact Registry repository name and image name 
# (you need to do this every time you build a new image)
docker tag mybay-be us-east4-docker.pkg.dev/ulaptop/ulaptop-repo/ulaptop-be

# push the Docker image to the Artifact Registry repository (you need to do this every time you build a new image)
docker push us-east4-docker.pkg.dev/ulaptop/ulaptop-repo/ulaptop-be