"""Application configuration management for FlowOps.

Loads configuration settings from environment variables or a local .env file.
Environment variables prefixed with FLOWOPS_ automatically map to their
respective settings fields (for example, FLOWOPS_AWS_REGION sets aws_region).
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Global settings for FlowOps.

    Attributes:
        app_name: The display name of the application.
        aws_region: Target AWS region for DynamoDB and S3 operations.
        aws_endpoint_url: Custom AWS endpoint URL, typically used for
            LocalStack or other local emulators during development and testing.
        s3_bucket: The S3 bucket name used for storing raw and processed datasets.
        dynamodb_table: The DynamoDB table name storing pipeline state records.
        demo_fixture: Default sample CSV filename located in the data directory.
    """
    app_name: str = "FlowOps"
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    s3_bucket: str = "flowops-data"
    dynamodb_table: str = "flowops-pipelines"
    demo_fixture: str = "demo.csv"

    model_config = SettingsConfigDict(
        env_prefix="FLOWOPS_",
        env_file=".env",
        extra="ignore",
    )


# Global settings instance used across the application.
settings = Settings()
