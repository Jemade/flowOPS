#!/bin/sh
set -eu
awslocal s3 mb s3://flowops-data || true
awslocal dynamodb create-table --table-name flowops-pipelines --attribute-definitions AttributeName=id,AttributeType=S --key-schema AttributeName=id,KeyType=HASH --billing-mode PAY_PER_REQUEST || true
