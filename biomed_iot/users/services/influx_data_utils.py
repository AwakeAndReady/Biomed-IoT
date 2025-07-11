"""
High-level data operations (read / delete / export) for a single user bucket/measurement.
"""

from __future__ import annotations

import csv
import io
import requests
from datetime import datetime
from django.utils import timezone
from typing import Iterator, Dict, Any, Tuple, List
from influxdb_client import InfluxDBClient
from influxdb_client.client.flux_table import FluxTable
from biomed_iot.config_loader import config


def to_rfc3339(value) -> str:
    """Return RFC-3339 string, *always* suffixed with 'Z'."""
    if isinstance(value, datetime):
        return value.isoformat() + "Z"
    if isinstance(value, str):
        return value if value.endswith("Z") else value + "Z"
    raise TypeError(f"Unsupported timestamp type: {type(value)}")


class InfluxDataManager:
    """
    Encapsulates InfluxDB calls for a user’s personal bucket
    (querying, deleting and exporting data).
    """

    def __init__(self, user):
        self.user = user
        self.org_id = config.influxdb.INFLUX_ORG_ID
        self.url = f"http://{config.influxdb.INFLUX_HOST}:{config.influxdb.INFLUX_PORT}"
        self.bucket = user.influxuserdata.bucket_name
        self.token = user.influxuserdata.bucket_token

    # ─────────────────────────── Private helpers ────────────────────────────
    def _client(self) -> InfluxDBClient:
        return InfluxDBClient(
            url=self.url,
            token=self.token,
            org=self.org_id,
            timeout=300_000  # e.g. 5 minutes = 300_000 ms
        )

    # services/influx_data_utils.py  (replace the helper)

    @staticmethod
    def _flatten_tables(flux_tables) -> List[Dict[str, Any]]:
        """
        Convert a sequence of Flux tables into a flat list of row-dicts,
        stripping out Flux metadata and underscore-prefixed keys.
        """
        METADATA_COLUMNS = {"result", "table"}
        flat_rows: List[Dict[str, Any]] = []

        for table in flux_tables:
            for record in table:
                # base fields every row will have
                row: Dict[str, Any] = {
                    "time":  record.get_time().isoformat(),
                    "field": record["_field"],
                    "value": record["_value"],
                }

                # include any non-meta, non-underscore tags/columns
                for column_name, column_value in record.values.items():
                    if column_name in METADATA_COLUMNS or column_name.startswith("_"):
                        continue
                    row[column_name] = column_value

                flat_rows.append(row)

        return flat_rows

    def _row_generator(self, record_stream: Iterator[Any]) -> Iterator[bytes]:
        """
        Take an iterator of FluxRecord, flatten each to a dict,
        write CSV header on first row, then yield each row as UTF-8 bytes.
        """
        buffer = io.StringIO()
        csv_writer: csv.DictWriter | None = None
        header_fields: list[str] | None = None

        # pick once outside the loop – respects TIME_ZONE or per-request activate()
        local_tz = timezone.get_current_timezone()

        for record in record_stream:
            # convert time from UTC → project/user zone
            local_time = timezone.localtime(record.get_time(), local_tz)
            # flatten a single FluxRecord to a simple dict
            row: Dict[str, Any] = {
                "time":      local_time.isoformat(),
                "field":     record["_field"],
                "value":     record["_value"],
            }
            for key, value in record.values.items():
                if key in {"result", "table"} or key.startswith("_"):
                    continue
                row[key] = value

            # initialize writer & header on first row
            if header_fields is None:
                header_fields = sorted(row.keys())
                csv_writer = csv.DictWriter(buffer, fieldnames=header_fields)
                # build a mapping of field → header label, adding " (tag)" for non-core fields
                header_labels = {
                    key: key if key in ("time", "field", "value")
                         else f"{key} (tag)"
                    for key in header_fields
                }
                # write Excel separator hint
                buffer.write("sep=,\n")
                # write custom header rows
                csv_writer.writerow(header_labels)
                yield buffer.getvalue().encode("utf-8")
                buffer.seek(0)
                buffer.truncate(0)

            # write the current row and yield bytes
            csv_writer.writerow(row)
            yield buffer.getvalue().encode("utf-8")
            buffer.seek(0)
            buffer.truncate(0)

        # no records at all?
        if header_fields is None:
            raise ValueError("No matching points")


    # ─────────────────────────── Public API ─────────────────────────────────
    def list_measurements(self) -> List[str]:
        """Return all distinct measurement names in this bucket."""

        flux_query = f'''
import "influxdata/influxdb/schema"
schema.measurements(
bucket: "{self.bucket}",
start: -inf
)
'''

        with self._client() as client:
            tables = client.query_api().query(flux_query)

        measurements: List[str] = []
        for table in tables:
            for record in table.records:
                # record.get_value() will be the measurement name (string)
                measurements.append(record.get_value())

#         flux_query = f"""
# from(bucket:"{self.bucket}")
#   |> range(start: 1970-01-01T00:00:00Z)
#   |> keep(columns: ["_measurement"])
#   |> distinct(column: "_measurement")
# """
#         with self._client() as client:
#             tables = client.query_api().query(flux_query)

#         # extract the measurement name from each row
#         measurements: List[str] = []
#         for table in tables:
#             for row in table:
#                 measurements.append(row["_value"])
        return measurements

    def delete(
        self,
        measurement: str,
        tags: Dict[str, str],
        start_iso: str,
        stop_iso: str,
        ) -> bool:
        """
        Delete all points matching the given measurement, tags, and time range.
        Returns True if the HTTP delete succeeded (204 status).
        """
        # build individual clauses like _measurement="foo" and tag1="bar"
        clauses = [f'_measurement="{measurement}"']
        for tag_key, tag_val in tags.items():
            clauses.append(f'{tag_key}="{tag_val}"')
        predicate = " AND ".join(clauses)

        delete_payload = {
            "start":     start_iso,
            "stop":      stop_iso,
            "predicate": predicate,
        }
        endpoint = f"{self.url}/api/v2/delete?org={self.org_id}&bucket={self.bucket}"
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Token {self.token}",
                "Content-Type":  "application/json",
            },
            json=delete_payload,
        )

        return response.status_code == 204

    def export_stream(
        self,
        measurement: str,
        tags: Dict[str, str],
        start_iso: str,
        stop_iso: str,
        ) -> Tuple[Iterator[bytes], str]:
        """
        Stream query results as CSV lines. Returns (csv_byte_iterator, filename).
        """
        # build Flux filter predicate
        filter_clauses = [
            f'r["{tag_name}"]=="{tag_value}"'
            for tag_name, tag_value in tags.items()
        ]
        measurement_predicate = f'r["_measurement"]=="{measurement}"'
        full_predicate = " and ".join([measurement_predicate] + filter_clauses)

        flux = f"""
from(bucket:"{self.bucket}")
  |> range(start:{start_iso}, stop:{stop_iso})
  |> filter(fn:(r) => {full_predicate})
"""

        client = self._client()
        record_stream = client.query_api().query_stream(flux)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"measurement_{measurement}_{timestamp}.csv"

        return self._row_generator(record_stream), filename

    def list_tag_keys(self, measurement: str) -> list[str]:
        """
        Return all tag _keys_ for this measurement, across all time,
        but exclude any Flux metadata columns (those that begin with "_").
        """
        flux = f'''
import "influxdata/influxdb/schema"

schema.tagKeys(
  bucket: "{self.bucket}",
  predicate: (r) => r._measurement == "{measurement}",
  start: 1970-01-01T00:00:00Z,
  stop: now()
)
'''
        tables = self._client().query_api().query(flux)
        # filter out any key starting with "_" so only real tags remain
        return [
            row["_value"]
            for table in tables
            for row in table
            if not row["_value"].startswith("_")
        ]

    def list_tag_values(self, measurement: str, tag_key: str) -> list[str]:
        """
        Return all tag _values_ for one tag key in this measurement, across all time.
        (No change needed here.)
        """
        flux = f'''
import "influxdata/influxdb/schema"

schema.tagValues(
  bucket: "{self.bucket}",
  tag: "{tag_key}",
  predicate: (r) => r._measurement == "{measurement}",
  start: 1970-01-01T00:00:00Z,
  stop: now()
)
'''
        tables = self._client().query_api().query(flux)
        return [row["_value"] for table in tables for row in table]



    def list_tag_pairs(self, measurement: str) -> list[str]:
        """
        Return all key=value strings for this measurement.
        """
        pairs: list[str] = []
        for key in self.list_tag_keys(measurement):
            for val in self.list_tag_values(measurement, key):
                pairs.append(f"{key}={val}")
        return pairs
