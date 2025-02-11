from collections import defaultdict
from math import isnan, nan

import numpy as np


def aggregate(run_data):
    omnibus = defaultdict(list)
    for entry in run_data:
        for k, v in entry.items():
            omnibus[k].append(v)

    (config,) = omnibus["#config"]

    device = config.get("device", None)
    omnibus["gpudata"] = [
        {str(device): entry[str(device)]} if device is not None else entry
        for entry in omnibus.get("gpudata", [])
        if device is None or str(device) in entry
    ]

    if device is not None:
        omnibus["per_gpu"] = [(device, tr) for tr in omnibus["train_rate"]]

    if "loss" in omnibus:
        fl, ll = omnibus["loss"][0], omnibus["loss"][-1]
        omnibus["loss_gain"] = [ll - fl]

    omnibus["walltime"] = [omnibus["#end"][-1] - omnibus["#start"][0]]
    omnibus["success"] = [
        omnibus.get("#return_code", [-1])[-1] == 0
        and not any(isnan(loss) for loss in omnibus.get("loss", []))
        # and omnibus.get("loss_gain", [-1])[-1] < 0
        and bool(omnibus.get("train_rate", []))
    ]

    return omnibus


def _classify(all_aggregates):
    classified = defaultdict(list)
    for agg in all_aggregates:
        (config,) = agg["#config"]
        classified[config["name"]].append(agg)
    return classified


def _merge(aggs):
    results = defaultdict(list)
    for agg in aggs:
        for k, v in agg.items():
            results[k].extend(v)
    return results


def _metrics(xs):
    if not xs:
        return {
            "min": nan,
            "q1": nan,
            "median": nan,
            "q3": nan,
            "max": nan,
            "mean": nan,
            "std": nan,
            "sem": nan,
        }
    percentiles = [0, 25, 50, 75, 100]
    percentile_names = ["min", "q1", "median", "q3", "max"]
    metrics = dict(zip(percentile_names, np.percentile(xs, percentiles)))
    metrics["mean"] = np.mean(xs)
    metrics["std"] = np.std(xs)
    metrics["sem"] = np.std(xs) / len(xs) ** 0.5
    return metrics


def _summarize(agg):
    gpudata = defaultdict(lambda: defaultdict(list))
    for entry in agg["gpudata"]:
        for device, data in entry.items():
            if data["memory"][0] == 1 or data["load"] == 0:
                continue
            gpudata[device]["memory"].append(data["memory"][0])
            gpudata[device]["load"].append(data["load"])

    per_gpu = defaultdict(list)
    for device, tr in agg["per_gpu"]:
        per_gpu[device].append(tr)

    config = agg["#config"][0]
    return {
        "name": config["name"],
        "n": len(agg["success"]),
        "successes": sum(agg["success"]),
        "failures": sum(not x for x in agg["success"]),
        "train_rate": _metrics(agg["train_rate"]),
        "walltime": _metrics(agg["walltime"]),
        "per_gpu": {
            device: _metrics(train_rates) for device, train_rates in per_gpu.items()
        },
        "gpu_load": {
            device: {
                "memory": _metrics(data["memory"]),
                "load": _metrics(data["load"]),
            }
            for device, data in gpudata.items()
        },
    }


def make_summary(runs):
    aggs = [aggregate(run) for run in runs]
    classified = _classify(aggs)
    merged = {name: _merge(runs) for name, runs in classified.items()}
    summarized = {name: _summarize(agg) for name, agg in merged.items()}
    return summarized
