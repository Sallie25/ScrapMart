"""Explicit opt-in lifecycle for the Batch 3B.3 disposable PostgreSQL fixture.

No dotenv, cloud configuration, host ports, host mounts or existing DB fixtures.
Run: python3 tests/run-isolated-postgres.py --run-isolated
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
NAME = "scrapmart-bff-3b3"
VOLUME = "scrapmart-bff-3b3-data"
IMAGE = "sha256:ca0bd484cb98bf4b24eb1010e73fb3fcbd6714d240fbc1a10eea5b7dbecb641d"
LABEL = "com.scrapmart.batch"
RUN_LABEL = "com.scrapmart.run"
DATABASE = "scrapmart_bff_local_test"


def command(*args, input_text=None, timeout=90, check=True):
    result = subprocess.run(args, cwd=ROOT, input=input_text, text=True,
                            capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"Command failed: {args[0:3]}: {result.stderr.strip()}")
    return result


def docker(*args, **kwargs):
    return command("docker", *args, **kwargs)


def names(kind):
    return set(docker(*kind, "--format", "{{.Name}}" if kind[0] == "volume" else "{{.Names}}").stdout.splitlines())


def inspect_container():
    # Explicit allowlist: never inspect Config.Env or print credentials.
    raw = docker("inspect", "--format", '{{json .Id}}\n{{json .Image}}\n'
                             '{{json .HostConfig.NetworkMode}}\n{{json .HostConfig.PortBindings}}\n'
                             '{{json .NetworkSettings.Ports}}\n{{json .Mounts}}\n'
                             '{{json .Config.Labels}}', NAME).stdout
    return [json.loads(line) for line in raw.splitlines()]


def verify(container_id, volume_meta, run_id):
    cid, image, network, bindings, ports, mounts, labels = inspect_container()
    assert cid == container_id and image == IMAGE, "Container/image identity mismatch"
    assert network == "none" and not bindings and not ports, "Network isolation mismatch"
    assert labels.get(LABEL) == "3b3" and labels.get(RUN_LABEL) == run_id, "Container labels mismatch"
    assert len(mounts) == 1, "Unexpected mount"
    mount = mounts[0]
    assert mount["Type"] == "volume" and mount["Name"] == VOLUME, "Volume mismatch"
    assert mount["Destination"] == "/var/lib/postgresql/data" and mount["RW"], "Mount mismatch"
    current = json.loads(docker("volume", "inspect", "--format", "{{json .}}", VOLUME).stdout)
    assert current == volume_meta, "Volume identity changed"
    assert current["Labels"].get(LABEL) == "3b3" and current["Labels"].get(RUN_LABEL) == run_id


def ready():
    for _ in range(60):
        if docker("exec", NAME, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", check=False).returncode == 0:
            return
        time.sleep(0.25)
    raise RuntimeError("Dedicated PostgreSQL did not become ready")


def main():
    if not __debug__:
        raise RuntimeError("Optimized Python disables isolation assertions; abort")
    if sys.argv[1:] != ["--run-isolated"]:
        raise RuntimeError("Explicit --run-isolated authorization flag required")
    assert command("git", "branch", "--show-current").stdout.strip() == "feature/frontend-buyer-vendor-integration"
    original_containers = names(("ps", "-a"))
    original_volumes = names(("volume", "ls"))
    assert NAME not in original_containers and VOLUME not in original_volumes, "Resource name collision; abort"
    actual_image = docker("image", "inspect", "--format", "{{.Id}}", "postgres@" + IMAGE).stdout.strip()
    assert actual_image == IMAGE, "Cached image mismatch"
    run_id = str(uuid.uuid4())
    container_id = None
    volume_meta = None
    try:
        docker("volume", "create", "--label", LABEL + "=3b3", "--label", RUN_LABEL + "=" + run_id, VOLUME)
        volume_meta = json.loads(docker("volume", "inspect", "--format", "{{json .}}", VOLUME).stdout)
        container_id = docker("run", "-d", "--pull=never", "--name", NAME,
                              "--label", LABEL + "=3b3", "--label", RUN_LABEL + "=" + run_id,
                              "--network", "none", "--mount", "type=volume,src=" + VOLUME + ",dst=/var/lib/postgresql/data",
                              "--env", "POSTGRES_HOST_AUTH_METHOD=trust", "--env", "POSTGRES_INITDB_ARGS=--auth-local=trust --auth-host=trust",
                              "postgres@" + IMAGE, "-c", "listen_addresses=127.0.0.1").stdout.strip()
        verify(container_id, volume_meta, run_id)
        print("PASS identity, pinned image, network=none, no published ports, dedicated labelled volume", flush=True)
        ready()
        # No host mounts: copy an allowlisted, secret-free fixture and existing JS driver.
        with tempfile.TemporaryDirectory(prefix="scrapmart-bff-fixture-") as folder:
            stage = Path(folder)
            for relative in ("src/lib/server/sessions", "tests/helpers"):
                shutil.copytree(ROOT / relative, stage / relative)
            for relative in ("tests/session-store.postgres.test.mjs", "tests/session-store.postgres-restart.mjs"):
                destination = stage / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / relative, destination)
            (stage / "ISOLATED.json").write_text(json.dumps({"batch": "3b3", "database": DATABASE, "run": run_id}))
            # Resolve exactly the installed pg dependency closure. No installs or dotenv.
            dependency_list = command("node", "-e", """
const fs=require('node:fs'),path=require('node:path');const found=new Set();
function walk(name,base){let dir=path.dirname(require.resolve(name,{paths:[base]}));
while(!fs.existsSync(path.join(dir,'package.json'))||JSON.parse(fs.readFileSync(path.join(dir,'package.json'))).name!==name){
const parent=path.dirname(dir);if(parent===dir)throw Error('Package root not found');dir=parent;}
if(found.has(dir))return;found.add(dir);
const p=JSON.parse(fs.readFileSync(path.join(dir,'package.json')));for(const d of Object.keys(p.dependencies||{}))walk(d,dir);}
walk('pg',process.cwd());console.log(JSON.stringify([...found]));
""").stdout
            for directory in json.loads(dependency_list):
                source = Path(directory)
                relative = source.relative_to(ROOT / "node_modules")
                shutil.copytree(source, stage / "node_modules" / relative)
            node = Path(shutil.which("node")).resolve()
            shutil.copyfile(node, stage / "node")
            os.chmod(stage / "node", 0o755)
            docker("cp", str(stage) + "/.", NAME + ":/tmp/bff")
        docker("exec", NAME, "/tmp/bff/node", "--version")
        verify(container_id, volume_meta, run_id)
        docker("exec", NAME, "createdb", "-U", "postgres", "--owner=postgres", DATABASE)
        docker("exec", "-i", NAME, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE,
               input_text=(ROOT / "db/bff-sessions/schema.sql").read_text())
        docker("exec", NAME, "psql", "-X", "-v", "ON_ERROR_STOP=1", "-U", "postgres", "-d", DATABASE,
               "-c", "ALTER ROLE scrapmart_bff_runtime LOGIN")
        print("PASS reviewed SQL applied; restricted local-only role enabled", flush=True)

        def node_test(script, phase=None, test=False):
            verify(container_id, volume_meta, run_id)
            args = ["exec", "-w", "/tmp/bff", NAME, "env", "-i", "SCRAPMART_BFF_ISOLATED_TEST=1",
                    "/tmp/bff/node", "--import", "./tests/helpers/session-loader.mjs"]
            if test:
                args += ["--test", "--test-isolation=none", "--test-timeout=20000"]
            args.append(script)
            if phase:
                args.append(phase)
            result = subprocess.run(["docker", *args], cwd=ROOT, timeout=90)
            if result.returncode:
                raise RuntimeError("Isolated PostgreSQL test phase failed")

        node_test("tests/session-store.postgres.test.mjs", test=True)
        node_test("tests/session-store.postgres-restart.mjs", "prepare")
        verify(container_id, volume_meta, run_id)
        docker("restart", NAME)
        ready()
        verify(container_id, volume_meta, run_id)
        node_test("tests/session-store.postgres-restart.mjs", "verify")
    finally:
        # All workers are synchronous docker exec subprocesses; timeout kills the
        # host CLI, so stop this exact container before removing its data volume.
        if container_id:
            verify(container_id, volume_meta, run_id)
            docker("stop", NAME)
            verify(container_id, volume_meta, run_id)
            docker("rm", container_id)
        if volume_meta:
            current = json.loads(docker("volume", "inspect", "--format", "{{json .}}", VOLUME).stdout)
            assert current == volume_meta and current["Labels"].get(RUN_LABEL) == run_id, "Cleanup volume mismatch"
            docker("volume", "rm", VOLUME)
        after_containers = names(("ps", "-a"))
        after_volumes = names(("volume", "ls"))
        assert NAME not in after_containers and VOLUME not in after_volumes
        assert original_containers <= after_containers and original_volumes <= after_volumes
        print("PASS cleanup: exact dedicated resources removed; pre-existing resource names preserved", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("FAIL:", str(error), file=sys.stderr)
        sys.exit(1)
