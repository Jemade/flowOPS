"""Storage abstractions for reading and writing pipeline datasets.

This module provides a unified interface for reading input datasets whether
they come from bundled fixtures, the local filesystem, or Amazon S3 buckets.
"""

from pathlib import Path
import csv
import io
import boto3
from .config import settings


class ObjectStorage:
    """Unified storage handler for CSV data files and cloud objects."""

    def __init__(self):
        self.client = None
        # Only initialize the boto3 S3 client if an endpoint is configured.
        # This prevents boto3 from making slow metadata service calls when
        # running in local test environments without AWS credentials.
        if settings.aws_endpoint_url:
            try:
                self.client = boto3.client(
                    "s3",
                    region_name=settings.aws_region,
                    endpoint_url=settings.aws_endpoint_url,
                )
            except Exception:
                self.client = None

    def read(self, source: str) -> str:
        """Reads content from a named fixture, S3 URI, or local filepath.

        Args:
            source: Source identifier. Supported formats include:
                - 'demo' or 'fixture': Loads the bundled demo dataset.
                - 's3://bucket/key': Downloads an object from S3.
                - Local filepath string: Reads directly from disk.

        Returns:
            The raw text content of the dataset.

        Raises:
            FileNotFoundError: If the fixture or local file cannot be found.
        """
        # Handle built-in demo fixtures
        if source in ("demo", "fixture"):
            path = Path("data") / settings.demo_fixture
            if path.exists():
                return path.read_text()
            raise FileNotFoundError(f"Fixture not found: {path}")

        # Handle Amazon S3 object paths
        if source.startswith("s3://") and self.client:
            bucket, key = source[5:].split("/", 1)
            response = self.client.get_object(Bucket=bucket, Key=key)
            return response["Body"].read().decode()

        # Handle local filesystem paths
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Source not found: {source}")
        return path.read_text()

    def write(self, key: str, content: str) -> None:
        """Writes content to the configured S3 bucket if a client is available.

        Args:
            key: Object key name within the target bucket.
            content: Raw string content to upload.
        """
        if self.client:
            try:
                self.client.put_object(
                    Bucket=settings.s3_bucket,
                    Key=key,
                    Body=content.encode(),
                )
            except Exception:
                pass


def parse_csv(text: str) -> list[dict[str, str]]:
    """Parses raw CSV text into a list of row dictionaries.

    Args:
        text: Raw CSV string with header row.

    Returns:
        List of dictionaries mapping column headers to string values.
    """
    return list(csv.DictReader(io.StringIO(text)))
