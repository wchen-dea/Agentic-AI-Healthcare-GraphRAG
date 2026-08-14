from __future__ import annotations

import os
import stat
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    bootstrap = REPO_ROOT / "neo4j" / "bootstrap.sh"
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        init_file = tmp_path / "init.cypher"
        generated_file = tmp_path / "generated.cypher"
        output_file = tmp_path / "bootstrap.cypher"
        cypher_log = tmp_path / "cypher-shell.log"
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()

        init_file.write_text("MERGE (:Condition {name: \"InitOnly\"});\n", encoding="utf-8")
        generated_file.write_text("MERGE (:Condition {name: \"GeneratedOnly\"});\n", encoding="utf-8")

        fake_cypher_shell = fake_bin / "cypher-shell"
        fake_cypher_shell.write_text(
            "#!/bin/sh\n"
            "printf '%s\n' \"$@\" > \"$BOOTSTRAP_CYPHER_LOG\"\n"
            "exit 0\n",
            encoding="utf-8",
        )
        fake_cypher_shell.chmod(fake_cypher_shell.stat().st_mode | stat.S_IXUSR)

        env = os.environ.copy()
        env.update(
            {
                "PATH": f"{fake_bin}:{env.get('PATH', '')}",
                "NEO4J_BOOTSTRAP_SLEEP_SECONDS": "0",
                "NEO4J_INIT_FILE": str(init_file),
                "NEO4J_GENERATED_SEEDS_FILE": str(generated_file),
                "NEO4J_BOOTSTRAP_OUTPUT": str(output_file),
                "BOOTSTRAP_CYPHER_LOG": str(cypher_log),
            }
        )

        result = subprocess.run(["/bin/sh", str(bootstrap)], cwd=REPO_ROOT, env=env, check=False)
        if result.returncode != 0:
            return result.returncode

        content = output_file.read_text(encoding="utf-8")
        if "InitOnly" not in content or "GeneratedOnly" not in content:
            raise SystemExit("bootstrap output did not include both init and generated seed content")

        cypher_args = cypher_log.read_text(encoding="utf-8")
        if str(output_file) not in cypher_args:
            raise SystemExit("cypher-shell was not invoked with the generated bootstrap file")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())