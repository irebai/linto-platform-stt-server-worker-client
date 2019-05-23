# Build Docker
docker build -t linagora/stt-offline .

# Start 
Path_model=$1
port=$2
model_type=$3

if [ -z "${model_type}" ]; then
    model_type="uc1"
fi

docker run --rm -it -p $port:5000 -v $Path_model:/opt/models -e MODEL_TYPE=$model_type linagora/stt-offline