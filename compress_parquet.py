#!/usr/bin/env python3
"""
Streaming re-compression of Parquet files in S3, in-place, with a chosen codec.

Instead of loading whole files into memory, this:
  1. Reads the source object directly from S3 via pyarrow's S3 filesystem
     (range reads -- only the footer + one row group at a time are fetched).
  2. Writes the re-encoded output directly to a temporary S3 key using a
     streaming multipart upload (pyarrow handles this under the hood).
  3. Atomically-ish swaps: server-side copies the temp object over the
     original key, then deletes the temp object.

Peak memory usage is roughly ONE (decompressed) row group, regardless of
total file size. Nothing is written to local disk.

Usage:
    # Single file
    python compress_s3_parquet.py --bucket my-bucket --key data/file.parquet --codec zstd

    # All parquet files under a prefix
    python compress_s3_parquet.py --bucket my-bucket --prefix data/2024/ --codec gzip

    # Dry run (re-encodes to the temp key to measure size, then deletes it;
    # the original is never touched)
    python compress_s3_parquet.py --bucket my-bucket --prefix data/ --codec zstd --dry-run

Supported codecs: snappy, gzip, zstd, brotli, lz4, none

Requirements:
    pip install boto3 pyarrow

Credentials come from the standard AWS chain (env vars, ~/.aws, IAM role).
"""

import argparse
import sys

import boto3
import pyarrow.fs as pafs
import pyarrow.parquet as pq

VALID_CODECS = {"snappy", "gzip", "zstd", "brotli", "lz4", "none"}
TMP_SUFFIX = ".recompress.tmp.parquet"


def list_parquet_keys(s3, bucket: str, prefix: str):
    """Yield all .parquet object keys under a prefix (skipping our temp files)."""
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if key.endswith(".parquet") and not key.endswith(TMP_SUFFIX):
                yield key, obj["Size"]


def stream_recompress(fs: pafs.S3FileSystem, s3, bucket: str, key: str,
                      codec: str, compression_level: int | None,
                      batch_rows: int | None, dry_run: bool) -> tuple[int, int]:
    """
    Stream-re-encode s3://bucket/key with the given codec.

    Reads one row group at a time from S3 and streams the output to a temp
    key via multipart upload. On success, copies the temp object over the
    original (server-side) and deletes the temp. Returns (old_size, new_size).
    """
    src_path = f"{bucket}/{key}"
    tmp_key = key + TMP_SUFFIX
    tmp_path = f"{bucket}/{tmp_key}"

    old_size = s3.head_object(Bucket=bucket, Key=key)["ContentLength"]

    compression = None if codec == "none" else codec
    writer_kwargs = {}
    if compression_level is not None and codec in ("zstd", "gzip", "brotli"):
        writer_kwargs["compression_level"] = compression_level

    try:
        # Open source with range-read access; only footer metadata is read here.
        with fs.open_input_file(src_path) as src:
            pf = pq.ParquetFile(src)

            # Streaming multipart upload to the temp key.
            with fs.open_output_stream(tmp_path) as sink:
                writer = pq.ParquetWriter(
                    sink, pf.schema_arrow,
                    compression=compression, **writer_kwargs,
                )
                try:
                    if batch_rows:
                        # Even finer-grained memory control: read in batches
                        # of N rows instead of whole row groups.
                        for batch in pf.iter_batches(batch_size=batch_rows):
                            writer.write_batch(batch)
                    else:
                        # One row group at a time (preserves row-group layout).
                        for rg in range(pf.num_row_groups):
                            writer.write_table(pf.read_row_group(rg))
                finally:
                    writer.close()

        new_size = s3.head_object(Bucket=bucket, Key=tmp_key)["ContentLength"]

        if not dry_run:
            # Server-side copy (managed transfer handles >5 GB via multipart
            # copy automatically), then remove the temp object.
            s3.copy({"Bucket": bucket, "Key": tmp_key}, bucket, key)

        return old_size, new_size
    finally:
        # Always clean up the temp object if it exists.
        try:
            s3.delete_object(Bucket=bucket, Key=tmp_key)
        except Exception:
            pass


def human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def main():
    parser = argparse.ArgumentParser(
        description="Stream-re-encode Parquet files in S3 with a chosen codec."
    )
    parser.add_argument("--bucket", required=True, help="S3 bucket name")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--key", help="Single object key to recompress")
    group.add_argument("--prefix", help="Recompress every .parquet under this prefix")
    parser.add_argument("--codec", required=True, choices=sorted(VALID_CODECS),
                        help="Target compression codec")
    parser.add_argument("--compression-level", type=int, default=None,
                        help="Optional level for zstd/gzip/brotli (e.g. zstd 1-22)")
    parser.add_argument("--batch-rows", type=int, default=None,
                        help="Read in batches of N rows instead of whole row "
                             "groups (lower memory for files with huge row groups)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Measure the re-encoded size without replacing the original")
    parser.add_argument("--region", default=None, help="AWS region (optional)")
    args = parser.parse_args()

    s3 = boto3.client("s3", region_name=args.region)
    region = args.region or s3.meta.region_name
    fs = pafs.S3FileSystem(region=region) if region else pafs.S3FileSystem()

    if args.key:
        targets = [(args.key, None)]
    else:
        targets = list(list_parquet_keys(s3, args.bucket, args.prefix))
        if not targets:
            print(f"No .parquet files found under s3://{args.bucket}/{args.prefix}")
            sys.exit(0)

    total_old = total_new = failures = 0

    for key, _ in targets:
        try:
            old, new = stream_recompress(
                fs, s3, args.bucket, key, args.codec,
                args.compression_level, args.batch_rows, args.dry_run,
            )
            total_old += old
            total_new += new
            pct = (1 - new / old) * 100 if old else 0
            tag = "[dry-run] " if args.dry_run else ""
            print(f"{tag}{key}: {human(old)} -> {human(new)} ({pct:+.1f}% saved)")
        except Exception as e:
            failures += 1
            print(f"ERROR {key}: {e}", file=sys.stderr)

    if total_old:
        pct = (1 - total_new / total_old) * 100
        print(f"\nTotal: {human(total_old)} -> {human(total_new)} "
              f"({pct:+.1f}% saved), {failures} failure(s)")

    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
