"""S3 utility module for interacting with AWS S3.

Provides the :class:`S3Handler` class which wraps common S3 operations
(upload, download, list, delete) using *boto3* with an async-style
interface.
"""

import boto3
import boto3.session


class S3Handler:
    """Handler for AWS S3 operations.

    Wraps a *boto3* session and exposes async convenience methods for
    uploading, downloading, listing, and deleting objects in a single
    S3 bucket.

    Attributes:
        _bucket_name: Name of the target S3 bucket.
        _session: Cached boto3 session instance.
        _region: AWS region for the session (defaults to ``us-east-1``).
    """

    _bucket_name: str | None = None
    _session: boto3.Session | None = None
    _region: str | None = None

    def __init__(self, bucket_name: str, region: str | None) -> None:
        """Initialise the S3Handler.

        Args:
            bucket_name: Name of the S3 bucket to operate on.
            region: AWS region name. Defaults to ``us-east-1`` when
                ``None``.

        Raises:
            ValueError: If *bucket_name* is ``None``.
        """
        if bucket_name is None:
            raise ValueError("bucket_name must be provided")
        if region is None:
            self._region = "us-east-1"
        else:
            self._region = region
        self._bucket_name = bucket_name

    async def _get_session(self) -> boto3.Session:
        """Return the cached boto3 session, creating it if necessary.

        Returns:
            A :class:`boto3.Session` configured with the handler's
            region.
        """
        if self._session is None:
            self._session = boto3.session.Session(region_name=self._region)
        return self._session

    async def upload_file(self, file_path: str, key: str) -> None:
        """Upload a local file to S3.

        Args:
            file_path: Absolute or relative path to the local file.
            key: S3 object key (destination path inside the bucket).
        """
        session = await self._get_session()
        s3_client = session.client("s3")
        s3_client.upload_file(file_path, self._bucket_name, key)

    async def download_file(self, key: str, file_path: str) -> None:
        """Download an S3 object to a local file.

        Args:
            key: S3 object key to download.
            file_path: Local destination path for the downloaded file.
        """
        session = await self._get_session()
        s3_client = session.client("s3")
        s3_client.download_file(self._bucket_name, key, file_path)

    async def list_files(self, prefix: str = "") -> list[str]:
        """List object keys in the bucket matching a prefix.

        Uses the S3 paginator to handle buckets with more than 1 000
        objects.

        Args:
            prefix: Key prefix to filter results. Defaults to ``""``
                (all objects).

        Returns:
            A list of S3 object keys matching the prefix.
        """
        session = await self._get_session()
        s3_client = session.client("s3")
        paginator = s3_client.get_paginator("list_objects_v2")
        page_iterator = paginator.paginate(Bucket=self._bucket_name, Prefix=prefix)
        files = []
        for page in page_iterator:
            if "Contents" in page:
                for obj in page["Contents"]:
                    files.append(obj["Key"])
        return files

    async def delete_file(self, key: str) -> None:
        """Delete an object from the bucket.

        Args:
            key: S3 object key to delete.
        """
        session = await self._get_session()
        s3_client = session.client("s3")
        s3_client.delete_object(Bucket=self._bucket_name, Key=key)
