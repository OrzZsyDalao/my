"""Build a fast atomic hop-pair inventory without repeating cable matching.

The inventory reconstructs the same geolocated, visible hop-pair population used
by Stage 1.  Post-processing joins it to retained feasible candidates to assign
one physical mapping-resolution state to every atomic segment.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from pathlib import Path
from typing import Any, Dict, Iterable

import maxminddb

from main_analysis import (
    ASN_MMDB_PATH,
    MMDB_PATH,
    PROBE_META_PATH,
    IPInfoASNResolver,
    build_trace_id,
    get_geo_info,
    iter_traceroute_results,
    load_probe_metadata,
    normalize_asn_value,
    select_hop_reply,
)
from measurement_catalog import lookup_measurement


INVENTORY_COLUMNS = [
    "atomic_segment_id",
    "trace_id",
    "msm_id",
    "probe_id",
    "probe_country",
    "probe_asn",
    "timestamp",
    "file_name",
    "service_id",
    "service_class",
    "service_entry_resolved",
    "path_scope",
    "hop_range",
    "source_ttl",
    "destination_ttl",
    "src_ip",
    "dst_ip",
    "src_country",
    "dst_country",
    "src_asn",
    "dst_asn",
    "rtt_delta_ms",
    "rtt_evidence_state",
    "segment_resolution_sufficient",
    "insufficient_resolution_reason",
]


def parse_args() -> argparse.Namespace:
    """Parse inventory CLI arguments."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--traceroute-input", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--probe-meta-file", default=PROBE_META_PATH)
    parser.add_argument("--asn-mmdb-path", default=ASN_MMDB_PATH)
    parser.add_argument(
        "--timeout-gap-policy",
        choices=["consecutive_only", "allow_timeout_bridged"],
        default="allow_timeout_bridged",
    )
    return parser.parse_args()


def build_atomic_segment_identifier(link: Dict[str, Any]) -> str:
    """Build the same stable hop-pair identifier used by post-processing."""
    hop_range = (
        f"Hop {link['source']['hop_num']} -> {link['destination']['hop_num']}"
    )
    return "|".join(
        [
            str(link.get("trace_id", "NA")),
            str(link.get("measurement_id", "NA")),
            str(link.get("probe_id", "NA")),
            str(link.get("timestamp", "NA")),
            hop_range,
            str(link["source"].get("ip", "NA")),
            str(link["destination"].get("ip", "NA")),
        ]
    )


def resolve_input_files(path: str | Path) -> Iterable[Path]:
    """Yield one or more traceroute JSON files."""
    input_path = Path(path)
    if input_path.is_file():
        yield input_path
        return
    for candidate in sorted(input_path.glob("*.json")):
        yield candidate


def build_observable_atomic_links(
    *,
    hops: list[Dict[str, Any]],
    msm_id: Any,
    probe_id: Any,
    timestamp: Any,
    file_name: str,
    mmdb_reader: Any,
    asn_resolver: IPInfoASNResolver,
    trace_metadata: Dict[str, Any],
    geo_cache: Dict[str, Dict[str, Any]],
    timeout_gap_policy: str,
) -> list[Dict[str, Any]]:
    """Retain every visible hop-pair, including insufficiently geolocated pairs."""
    hop_infos: list[Dict[str, Any] | None] = []
    for hop_data in hops:
        selected = select_hop_reply(hop_data)
        if not selected:
            hop_infos.append(None)
            continue
        ip = selected["ip"]
        geo = get_geo_info(ip, mmdb_reader, asn_resolver, geo_cache=geo_cache)
        hop_infos.append(
            {
                "ip": ip,
                "rtt": selected["rtt"],
                "geo": geo,
                "asn": normalize_asn_value(geo.get("asn")),
                "hop_num": hop_data["hop"],
            }
        )

    target_asn = normalize_asn_value(trace_metadata.get("target_asn"))
    service_entry_hop = None
    if target_asn != "-1":
        for hop_info in hop_infos:
            if hop_info and hop_info.get("asn") == target_asn:
                service_entry_hop = int(hop_info["hop_num"])
                break
    resolved_entry = service_entry_hop is not None
    path_scope = (
        "client_to_service_entry"
        if resolved_entry
        else "publicly_visible_path_unresolved_entry"
    )

    links: list[Dict[str, Any]] = []
    previous: Dict[str, Any] | None = None
    for current in hop_infos:
        if current is None:
            continue
        if service_entry_hop is not None and int(current["hop_num"]) > service_entry_hop:
            break
        if previous is not None:
            source_ttl = int(previous["hop_num"])
            destination_ttl = int(current["hop_num"])
            hop_gap = max(destination_ttl - source_ttl, 1)
            if timeout_gap_policy == "allow_timeout_bridged" or hop_gap == 1:
                links.append(
                    {
                        "source": previous,
                        "destination": current,
                        "rtt_delta": float(current["rtt"]) - float(previous["rtt"]),
                        "measurement_id": msm_id,
                        "probe_id": probe_id,
                        "timestamp": timestamp,
                        "file_name": file_name,
                        "trace_id": trace_metadata["trace_id"],
                        "service_entry_resolved": resolved_entry,
                        "path_scope": path_scope,
                    }
                )
        previous = current
    return links


def main() -> None:
    """Write a compressed, one-row-per-atomic-segment inventory."""
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "atomic_segment_inventory.csv.gz"
    probe_metadata = load_probe_metadata(args.probe_meta_file)
    asn_resolver = IPInfoASNResolver(args.asn_mmdb_path)
    geo_cache: Dict[str, Dict[str, Any]] = {}
    seen_trace_ids: set[str] = set()
    raw_results = 0
    valid_traces = 0
    atomic_segments = 0
    mappable_atomic_segments = 0
    insufficient_atomic_segments = 0

    with (
        maxminddb.open_database(MMDB_PATH) as mmdb_reader,
        gzip.open(output_path, "wt", encoding="utf-8-sig", newline="") as handle,
    ):
        writer = csv.DictWriter(handle, fieldnames=INVENTORY_COLUMNS)
        writer.writeheader()
        for input_file in resolve_input_files(args.traceroute_input):
            for raw_result in iter_traceroute_results(str(input_file)):
                raw_results += 1
                hops = raw_result.get("result") or []
                if not hops:
                    continue
                msm_id = raw_result.get("msm_id", "N/A")
                probe_id = raw_result.get("prb_id", "N/A")
                timestamp = (
                    raw_result.get("timestamp")
                    or raw_result.get("endtime")
                    or raw_result.get("starttime")
                    or "N/A"
                )
                target_ip = (
                    raw_result.get("dst_addr")
                    or raw_result.get("dst_ip")
                    or raw_result.get("target_ip")
                    or raw_result.get("dst_name")
                )
                target_asn = asn_resolver.get(target_ip) if target_ip else "-1"
                trace_id = build_trace_id(
                    input_file.name,
                    msm_id,
                    probe_id,
                    timestamp,
                    target_ip,
                )
                if trace_id in seen_trace_ids:
                    continue
                seen_trace_ids.add(trace_id)
                valid_traces += 1
                probe_meta = probe_metadata.get(str(probe_id), {})
                probe_country = (
                    raw_result.get("probe_country")
                    or raw_result.get("prb_country")
                    or raw_result.get("country_code")
                    or probe_meta.get("probe_country")
                )
                probe_asn = normalize_asn_value(
                    raw_result.get("probe_asn")
                    or raw_result.get("prb_asn")
                    or raw_result.get("asn_v4")
                    or probe_meta.get("probe_asn")
                )
                service_meta = lookup_measurement(msm_id)
                trace_metadata = {
                    "trace_id": trace_id,
                    "service_id": service_meta["service_id"],
                    "service_class": service_meta["service_class"],
                    "probe_country": probe_country,
                    "probe_asn": probe_asn,
                    "target_ip": target_ip,
                    "target_asn": target_asn,
                    "service_entry_resolved": False,
                    "path_scope": "publicly_visible_path_unresolved_entry",
                }
                links = build_observable_atomic_links(
                    hops=hops,
                    msm_id=msm_id,
                    probe_id=probe_id,
                    timestamp=timestamp,
                    file_name=input_file.name,
                    mmdb_reader=mmdb_reader,
                    asn_resolver=asn_resolver,
                    trace_metadata=trace_metadata,
                    geo_cache=geo_cache,
                    timeout_gap_policy=args.timeout_gap_policy,
                )
                for link in links:
                    rtt_delta = link.get("rtt_delta")
                    try:
                        rtt_conclusive = math.isfinite(float(rtt_delta)) and float(rtt_delta) > 0
                    except (TypeError, ValueError):
                        rtt_conclusive = False
                    src_country = link["source"]["geo"].get("country")
                    dst_country = link["destination"]["geo"].get("country")
                    insufficient_reasons = []
                    if not src_country:
                        insufficient_reasons.append("missing_src_country")
                    if not dst_country:
                        insufficient_reasons.append("missing_dst_country")
                    row = {
                        "atomic_segment_id": build_atomic_segment_identifier(link),
                        "trace_id": trace_id,
                        "msm_id": msm_id,
                        "probe_id": probe_id,
                        "probe_country": probe_country,
                        "probe_asn": probe_asn,
                        "timestamp": timestamp,
                        "file_name": input_file.name,
                        "service_id": service_meta["service_id"],
                        "service_class": service_meta["service_class"],
                        "service_entry_resolved": bool(link.get("service_entry_resolved")),
                        "path_scope": link.get("path_scope"),
                        "hop_range": (
                            f"Hop {link['source']['hop_num']} -> "
                            f"{link['destination']['hop_num']}"
                        ),
                        "source_ttl": link.get("source_ttl"),
                        "destination_ttl": link.get("destination_ttl"),
                        "src_ip": link["source"].get("ip"),
                        "dst_ip": link["destination"].get("ip"),
                        "src_country": src_country,
                        "dst_country": dst_country,
                        "src_asn": normalize_asn_value(link["source"].get("asn")),
                        "dst_asn": normalize_asn_value(link["destination"].get("asn")),
                        "rtt_delta_ms": rtt_delta,
                        "rtt_evidence_state": (
                            "rtt_conclusive" if rtt_conclusive else "rtt_inconclusive"
                        ),
                        "segment_resolution_sufficient": not insufficient_reasons,
                        "insufficient_resolution_reason": ",".join(insufficient_reasons),
                    }
                    writer.writerow(row)
                    atomic_segments += 1
                    if insufficient_reasons:
                        insufficient_atomic_segments += 1
                    else:
                        mappable_atomic_segments += 1

    manifest_path = output_dir / "atomic_segment_inventory_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "raw_results_total": raw_results,
                "valid_traces_total": valid_traces,
                "observable_atomic_segments_total": atomic_segments,
                "mappable_atomic_segments_total": mappable_atomic_segments,
                "insufficiently_resolved_atomic_segments_total": insufficient_atomic_segments,
                "counting_units": {
                    "raw_results_total": "traceroute result",
                    "valid_traces_total": "non-empty unique traceroute",
                    "observable_atomic_segments_total": "visible hop-pair",
                    "mappable_atomic_segments_total": "visible hop-pair with country labels at both ends",
                    "insufficiently_resolved_atomic_segments_total": "visible hop-pair lacking a country label at either end",
                },
                "input": str(args.traceroute_input),
                "output": str(output_path),
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(
        f"Saved atomic segment inventory to {output_path}: "
        f"raw_results={raw_results}, valid_traces={valid_traces}, "
        f"atomic_segments={atomic_segments}"
    )


if __name__ == "__main__":
    main()
