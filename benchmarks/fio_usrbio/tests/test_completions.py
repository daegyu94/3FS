"""Run real fio engine callbacks with a local, non-storage USRBIO error fixture."""

import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--fio", type=Path, required=True)
parser.add_argument("--baseline-engine", type=Path, required=True)
parser.add_argument("--patched-engine", type=Path, required=True)
parser.add_argument("--mock-library", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
results = []
with tempfile.TemporaryDirectory(prefix="fio-completion-") as tmp:
    file = Path(tmp) / "fixture"
    file.write_bytes(bytes(65536))
    for variant, engine in [
        ("baseline", args.baseline_engine),
        ("patched", args.patched_engine),
    ]:
        for injected in ["success", "error", "short"]:
            env = dict(os.environ)
            env["LD_PRELOAD"] = str(args.mock_library.resolve())
            env.pop("INJECT_USRBIO_ERROR", None)
            env.pop("INJECT_USRBIO_SHORT", None)
            if injected == "error":
                env["INJECT_USRBIO_ERROR"] = "1"
            if injected == "short":
                env["INJECT_USRBIO_SHORT"] = "1"
            fixture_log = Path(tmp) / (variant + "-" + injected + ".log")
            env["COMPLETION_FIXTURE_LOG"] = str(fixture_log)
            command = [
                str(args.fio.resolve()),
                "--name=completion-fixture",
                "--thread=1",
                "--ioengine=external:" + str(engine.resolve()),
                "--mountpoint=/mock-no-storage",
                "--filename=" + str(file),
                "--rw=read",
                "--bs=4096",
                "--size=65536",
                "--iodepth=4",
                "--iodepth_batch_submit=4",
                "--iodepth_batch_complete_min=4",
                "--iodepth_batch_complete_max=4",
                "--output-format=json",
            ]
            p = subprocess.run(
                command,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=15,
            )
            (args.output / f"{variant}-{injected}.txt").write_text(p.stdout)
            result = {
                "variant": variant,
                "fixture": injected,
                "returncode": p.returncode,
            }
            start = p.stdout.find("{\n")
            if start >= 0:
                report = json.loads(p.stdout[start:])
                result["errors"] = [j["error"] for j in report["jobs"]]
                result["read_bytes"] = sum(
                    j["read"]["io_bytes"] for j in report["jobs"]
                )
                result["short_ios"] = sum(
                    j["read"]["short_ios"] for j in report["jobs"]
                )
            result["actual_mock_completion_bytes"] = sum(
                max(0, int(v)) for v in fixture_log.read_text().splitlines()
            )
            results.append(result)
            if variant == "patched":
                if injected == "error":
                    assert p.returncode != 0 and result["errors"] == [5], result
                else:
                    assert p.returncode == 0, result
                    if injected == "short":
                        # fio 3.42 requeues residuals before accounting initial bytes.
                        assert result["short_ios"] == 1, result
                        assert result["actual_mock_completion_bytes"] == 65536, result
                        assert result["read_bytes"] == 65536 - 2048, result
                    else:
                        assert (
                            result["read_bytes"]
                            == result["actual_mock_completion_bytes"]
                        ), result
print(
    json.dumps(
        {
            "level": "local mocked completion correctness; not 3FS performance",
            "results": results,
        },
        indent=2,
    )
)
