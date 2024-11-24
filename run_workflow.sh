#!/usr/bin/env bash

gh workflow run build_and_release.yaml --ref=$(git branch --no-color -q|grep "*"|awk '{print $2}')
sleep 3
while true; do
    run_status=$(gh run list --workflow=build_and_release.yaml -L 1 --json status |jq -r '.[0].status')
    if [[ "$run_status" == "completed" ]]; then
        break
    fi
    printf "$run_status\r"
    sleep 1
done
gh run list --workflow=build_and_release.yaml -L 1
