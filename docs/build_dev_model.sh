#!/usr/bin/env bash
# This script is used to build the development version of the H3xrecon docker images.
# It will use the local source code instead of cloning the repository.

trap 'echo Exited!; exit;' SIGINT SIGTERM

H3XRECON_BASE_DIRECTORY=$(pwd)

SOURCE_PGSQL_DIR="${H3XRECON_SOURCE_PATH}/h3xrecon/docker/pgsql" # Change this to your local h3xrecon/docker/pgsql directory
DOCKER_BUILD_DIR="${H3XRECON_BASE_DIRECTORY}/build"
PYTHON_BUILD_DIR="${H3XRECON_BASE_DIRECTORY}/dist"
IMAGE_TAG="ghcr.io/h3xitsec/h3xrecon_"
TAG="dev"

function build() {
    rm -rf ${DOCKER_BUILD_DIR}
    rm -rf ${PYTHON_BUILD_DIR}
    prepare_local_environment
    build_docker_images
}

function prepare_local_environment() {
    echo "======================================="
    echo "    Preparing local environment...     "
    echo "======================================="

    mkdir -p ${PYTHON_BUILD_DIR}
    rm -rf .venv
    python -m venv .venv --prompt h3xrecon_dev

    # create source directories
    cp -r ${H3XRECON_SOURCE_PATH}/h3xrecon-{core,plugins,server,worker,cli} ${PYTHON_BUILD_DIR}/

    # remove requirements.txt and create new one
    rm -f ./.requirements.txt
    rm -f ./requirements.txt
    for c in core plugins server worker cli; do
        if [ -f ${PYTHON_BUILD_DIR}/h3xrecon-${c}/requirements.txt ]; then
            cat ${PYTHON_BUILD_DIR}/h3xrecon-${c}/requirements.txt >> ./.requirements.txt
            echo -e "\n" >> ./.requirements.txt
        fi
    done
    cat ./.requirements.txt  | grep -v h3xrecon| sort | uniq > ./requirements.txt

    # install dependencies
    ./.venv/bin/pip install --no-cache-dir -r ./requirements.txt

    # copy additional files
    cp -r ${H3XRECON_SOURCE_PATH}/h3xrecon/bin ./
    cp -r ${H3XRECON_SOURCE_PATH}/h3xrecon/docker-compose.local.yaml ./
    cp -r ${H3XRECON_SOURCE_PATH}/h3xrecon/docker ./

    # activate virtual environment with custom python path
    sed -i '
    /^deactivate () {/a\
        if [ -n "${_OLD_VIRTUAL_PYTHONPATH:-}" ] ; then\
            PYTHONPATH="${_OLD_VIRTUAL_PYTHONPATH:-}"\
            export PYTHONPATH\
            unset _OLD_VIRTUAL_PYTHONPATH\
        else\
            unset PYTHONPATH\
        fi
    /^hash -r 2> \/dev\/null$/a\
    \
    # Set up PYTHONPATH to include all h3xrecon components\
    _OLD_VIRTUAL_PYTHONPATH="${PYTHONPATH:-}"\
    PYTHONPATH="$VIRTUAL_ENV/../dist/h3xrecon-cli/src:$VIRTUAL_ENV/../dist/h3xrecon-worker/src:$VIRTUAL_ENV/../dist/h3xrecon-server/src:$VIRTUAL_ENV/../dist/h3xrecon-plugins/src:$VIRTUAL_ENV/../dist/h3xrecon-core/src"\
    export PYTHONPATH
    ' .venv/bin/activate
}

function build_docker_images() {
    echo "======================================="
    echo "    Building H3xrecon Docker Images    "
    echo "======================================="

    mkdir -p ${DOCKER_BUILD_DIR}/server
    mkdir -p ${DOCKER_BUILD_DIR}/worker

    # Copy files for server image
    for c in core plugins server; do
        rsync -rav --delete --progress --no-owner --no-group --exclude='h3xrecon_${c}.egg-info' --exclude='.git' --exclude='__pycache__' --exclude='venv' --exclude='build' "${H3XRECON_SOURCE_PATH}/h3xrecon-${c}" ${DOCKER_BUILD_DIR}/server/ | sed '0,/^$/d'
    done
    cp "${H3XRECON_SOURCE_PATH}/h3xrecon-server/requirements.txt" ${DOCKER_BUILD_DIR}/server/
    cp "${H3XRECON_SOURCE_PATH}/h3xrecon-server/Dockerfile" ${DOCKER_BUILD_DIR}/server/

    #Copy files for worker image
    for c in core plugins worker; do
        mkdir -p ${DOCKER_BUILD_DIR}/worker/h3xrecon_${c}
        cp -r "${H3XRECON_SOURCE_PATH}/h3xrecon-${c}" ${DOCKER_BUILD_DIR}/worker/
    done
    cp "${H3XRECON_SOURCE_PATH}/h3xrecon-worker/requirements.txt" ${DOCKER_BUILD_DIR}/worker/
    cp "${H3XRECON_SOURCE_PATH}/h3xrecon-worker/Dockerfile" ${DOCKER_BUILD_DIR}/worker/

    # Copy files for pgsql image
    cp -r "${SOURCE_PGSQL_DIR}" ${DOCKER_BUILD_DIR}/pgsql/

    for c in pgsql server worker; do
        printf "Building ${IMAGE_TAG}${c}:${TAG}.... "
        if ! docker buildx build -D --output type=docker --file ${DOCKER_BUILD_DIR}/${c}/Dockerfile --platform linux/amd64 --tag ${IMAGE_TAG}${c}:${TAG} ${DOCKER_BUILD_DIR}/${c}/ ; then #> /dev/null 2>&1; then
            echo "Failed to build ${IMAGE_TAG}${c}:${TAG}"
            exit 1
        fi
        printf "Done\n"
    done

    echo "======================================="
    echo "    Docker image built successfully!   "
    echo "======================================="
}

# Check if the current script is different from the copied script
function main() {
    if [[ -z "${H3XRECON_SOURCE_PATH}" ]]; then
        echo "H3XRECON_SOURCE_PATH is not set. Please set it to the path of the h3xrecon source code."
        exit 1
    fi
    if ! cmp -s ./build.sh ${H3XRECON_SOURCE_PATH}/h3xrecon/docs/build_dev_model.sh; then
        echo "Build script has changed. Updating and restarting..."
        cp ${H3XRECON_SOURCE_PATH}/h3xrecon/docs/build_dev_model.sh ./build.sh
        ./build.sh
    else
        echo "Build script is up to date."
    fi
    build
}

main