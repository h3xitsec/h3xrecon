!/usr/bin/env bash
# This script uses rsync to synchronize the source from the source directory to your dev directory
# It allow to easily run new code from the dev environment. It is also used by the build_dev.sh script

function main() {
    if [[ -z "${H3XRECON_SOURCE_PATH}" ]]; then
        echo "H3XRECON_SOURCE_PATH is not set. Please set it to the path of the h3xrecon source code."
        exit 1
    fi
    if [[ -z "${H3XRECON_DEV_PATH}" ]]; then
        echo "H3XRECON_DEV_PATH is not set. Please set it to the path of the h3xrecon development directory."
        exit 1
    fi
    for c in core server plugins worker cli; do 
        rsync -rav --delete --progress --no-owner --no-group --exclude='h3xrecon_${c}.egg-info' --exclude='.git' --exclude='__pycache__' --exclude='venv' --exclude='build' "${H3XRECON_SOURCE_PATH}/h3xrecon-${c}" ${H3XRECON_DEV_PATH}/dist | sed '0,/^$/d'
    done
    cp ${H3XRECON_SOURCE_PATH}/h3xrecon/docker-compose.local.yaml ${H3XRECON_DEV_PATH}/
    cp ${H3XRECON_SOURCE_PATH}/h3xrecon/bin/build_dev.sh ${H3XRECON_DEV_PATH}/build.sh
}

main