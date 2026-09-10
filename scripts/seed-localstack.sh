#!/bin/sh
set -eu

# LocalStack initialization script.
# Automatically executed on container startup when mounted to /etc/localstack/init/ready.d.

# Provision the default S3 bucket for dataset storage
awslocal s3 mb s3://flowops-data || true

# Create the DynamoDB table for pipeline state tracking
awslocal dynamodb create-table \
  --table-name flowops-pipelines \
  --attribute-definitions AttributeName=id,AttributeType=S \
  --key-schema AttributeName=id,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST || true
