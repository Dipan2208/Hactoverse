import json
import os
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path


RUNNER_IMAGE = os.environ.get("RUNNER_IMAGE", "hacktoverse-runner:local")
MAX_CODE_BYTES = 64 * 1024
MAX_CASES = 100
MAX_TEST_DATA_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
SUPPORTED_LANGUAGES = {"python3", "c", "cpp", "java"}
RUNNER_SLOTS = threading.BoundedSemaphore(2)


class RunnerUnavailable(Exception):
    pass


def _docker_executable():
    docker = shutil.which("docker")
    if docker:
        return docker
    if os.name == "nt":
        program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
        candidate = Path(program_files) / "Docker" / "Docker" / "resources" / "bin" / "docker.exe"
        if candidate.is_file():
            return str(candidate)
    return None


def runner_available():
    docker = _docker_executable()
    if not docker:
        return False
    try:
        result = subprocess.run(
            [docker, "image", "inspect", RUNNER_IMAGE],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _validate_request(language, code, tests):
    if language not in SUPPORTED_LANGUAGES:
        raise ValueError("Unsupported language")
    if not isinstance(code, str) or not code.strip():
        raise ValueError("Write some code before running")
    if len(code.encode("utf-8")) > MAX_CODE_BYTES:
        raise ValueError("Code exceeds the 64 KB limit")
    if not isinstance(tests, list) or not tests or len(tests) > MAX_CASES:
        raise ValueError(f"Provide between 1 and {MAX_CASES} test cases")
    total_bytes = 0
    for test in tests:
        if not isinstance(test, dict) or not isinstance(test.get("input", ""), str):
            raise ValueError("Invalid test case input")
        expected = test.get("expected", "")
        if not isinstance(expected, str):
            raise ValueError("Invalid expected output")
        total_bytes += len(test.get("input", "").encode("utf-8"))
        total_bytes += len(expected.encode("utf-8"))
    if total_bytes > MAX_TEST_DATA_BYTES:
        raise ValueError("Test case data exceeds the 1 MB limit")


def _run_isolated(language, code, tests, time_limit_sec):
    if not RUNNER_SLOTS.acquire(timeout=1):
        raise RunnerUnavailable("The isolated runner is busy. Please try again shortly.")
    try:
        return _run_isolated_container(language, code, tests, time_limit_sec)
    finally:
        RUNNER_SLOTS.release()


def _run_isolated_container(language, code, tests, time_limit_sec):
    docker = _docker_executable()
    if not docker:
        raise RunnerUnavailable("Docker is not installed; code execution remains disabled.")

    payload = json.dumps({
        "language": language,
        "code": code,
        "tests": tests,
        "time_limit_sec": time_limit_sec,
    }).encode("utf-8")
    if len(payload) > MAX_REQUEST_BYTES:
        raise ValueError("Runner request exceeds the 2 MB limit")

    timeout = min(
        120,
        20 + max(1, min(float(time_limit_sec or 2), 15)) * len(tests),
    )
    with tempfile.TemporaryDirectory(prefix="hacktoverse-runner-") as directory:
        cidfile = os.path.join(directory, "container-id")
        command = [
            docker, "run", "--pull=never", "--rm", "--interactive", "--init",
            "--network", "none",
            "--read-only",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "--pids-limit", "64",
            "--memory", "512m",
            "--memory-swap", "512m",
            "--cpus", "1",
            "--user", "10001:10001",
            "--ulimit", "nofile=64:64",
            "--ulimit", "fsize=10485760:10485760",
            "--ulimit", "core=0:0",
            "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=128m",
            "--tmpfs", "/dev/shm:rw,nosuid,nodev,noexec,size=16m",
            "--cidfile", cidfile,
            RUNNER_IMAGE,
        ]
        try:
            result = subprocess.run(
                command,
                input=payload,
                capture_output=True,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            if os.path.exists(cidfile):
                try:
                    with open(cidfile, encoding="ascii") as container_file:
                        container_id = container_file.read().strip()
                except OSError as cleanup_error:
                    raise RunnerUnavailable(
                        "The isolated runner timed out and its container could not be identified for cleanup."
                    ) from cleanup_error
                if container_id:
                    try:
                        cleanup = subprocess.run(
                            [docker, "rm", "--force", container_id],
                            capture_output=True,
                            timeout=5,
                            check=False,
                        )
                    except (OSError, subprocess.TimeoutExpired) as cleanup_error:
                        raise RunnerUnavailable(
                            "The isolated runner timed out and its container could not be stopped."
                        ) from cleanup_error
                    if cleanup.returncode != 0 and b"No such container" not in cleanup.stderr:
                        raise RunnerUnavailable(
                            "The isolated runner timed out and its container could not be stopped."
                        ) from error
            raise RunnerUnavailable("The isolated runner did not respond in time.") from error
        except OSError as error:
            raise RunnerUnavailable(f"Could not start Docker: {error}") from error

    if result.returncode != 0:
        details = result.stderr.decode("utf-8", "replace")[-2000:]
        raise RunnerUnavailable(details or "The isolated runner failed.")
    if len(result.stdout) > MAX_RESPONSE_BYTES:
        raise RunnerUnavailable("The isolated runner returned an oversized response.")
    try:
        response = json.loads(result.stdout)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RunnerUnavailable("The isolated runner returned an invalid response.") from error
    results = response.get("results") if isinstance(response, dict) else None
    if not isinstance(results, list) or any(not isinstance(item, dict) for item in results):
        raise RunnerUnavailable("The isolated runner returned an invalid response.")
    return response


def run_code(language, code, stdin_text="", time_limit_sec=2):
    tests = [{"input": stdin_text, "expected": ""}]
    _validate_request(language, code, tests)
    response = _run_isolated(language, code, tests, time_limit_sec)
    if response.get("compile_error"):
        return {
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "compile_error": response["compile_error"],
            "returncode": None,
        }
    if len(response["results"]) != 1:
        raise RunnerUnavailable("The isolated runner returned an invalid result count.")
    return response["results"][0]


def run_tests(language, code, tests, time_limit_sec=2):
    _validate_request(language, code, tests)
    return _run_isolated(language, code, tests, time_limit_sec)
