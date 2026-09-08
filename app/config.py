from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FlowOps"
    aws_region: str = "us-east-1"
    aws_endpoint_url: str | None = None
    s3_bucket: str = "flowops-data"
    dynamodb_table: str = "flowops-pipelines"
    demo_fixture: str = "demo.csv"
    model_config = SettingsConfigDict(env_prefix="FLOWOPS_", env_file=".env", extra="ignore")


settings = Settings()
