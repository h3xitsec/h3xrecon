#!/usr/bin/env bash

export GIT_DISCOVERY_ACROSS_FILESYSTEM=1

if [ -z "$1" ]; then
    echo "Usage: $0 <image>"
    exit 1
fi

image="${1}"

function build_push_image() {
    gh workflow run build-push-${image}.yaml --ref=$(git branch --no-color -q|grep "*"|awk '{print $2}')
    sleep 3
    while true; do
        run_status=$(gh run list --workflow=build-push-${image}.yaml -L 1 --json status |jq -r '.[0].status')
        if [[ "$run_status" == "completed" ]]; then
            break
        fi
        printf "$run_status\r"
        sleep 1
    done
    gh run list --workflow=build-push-${image}.yaml -L 1
}

build_push_image