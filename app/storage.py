from pathlib import Path
import csv
import io
import boto3
from .config import settings


class ObjectStorage:
    def __init__(self):
        self.client = None
        # Avoid contacting instance metadata in local/test environments.
        if settings.aws_endpoint_url:
            try:
                self.client = boto3.client("s3", region_name=settings.aws_region,
                                           endpoint_url=settings.aws_endpoint_url)
            except Exception:
                pass

    def read(self, source: str) -> str:
        if source in ("demo", "fixture"):
            path = Path("data") / settings.demo_fixture
            if path.exists():
                return path.read_text()
            raise FileNotFoundError(f"Fixture not found: {path}")
        if source.startswith("s3://") and self.client:
            bucket, key = source[5:].split("/", 1)
            return self.client.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        return path.read_text()

    def write(self, key: str, content: str) -> None:
        if self.client:
            try:
                self.client.put_object(Bucket=settings.s3_bucket, Key=key, Body=content.encode())
            except Exception:
                pass


def parse_csv(text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(text)))
