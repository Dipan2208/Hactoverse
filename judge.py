import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit


RUNNER_IMAGE = os.environ.get("RUNNER_IMAGE", "hacktoverse-runner:local")
RUNNER_BACKEND = os.environ.get("CODE_RUNNER_BACKEND", "docker").strip().lower()
JUDGE0_API_URL = os.environ.get("JUDGE0_API_URL", "https://judge0-ce.p.rapidapi.com").rstrip("/")
JUDGE0_API_KEY = os.environ.get("JUDGE0_API_KEY", "")
JUDGE0_API_HOST = urlsplit(JUDGE0_API_URL).hostname or ""
JUDGE0_ALLOWED_API_HOST = "judge0-ce.p.rapidapi.com"
MAX_CODE_BYTES = 64 * 1024
MAX_CASES = 100
MAX_TEST_DATA_BYTES = 1024 * 1024
MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_JUDGE0_BATCH_SIZE = 10
JUDGE0_TOTAL_TIMEOUT_SEC = 55
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
    if RUNNER_BACKEND == "judge0":
        parsed_url = urlsplit(JUDGE0_API_URL)
        try:
            valid_port = parsed_url.port in (None, 443)
        except ValueError:
            valid_port = False
        return bool(
            JUDGE0_API_KEY
            and parsed_url.scheme == "https"
            and parsed_url.hostname == JUDGE0_ALLOWED_API_HOST
            and valid_port
            and not parsed_url.username
            and not parsed_url.password
            and not parsed_url.query
            and not parsed_url.fragment
        )
    if RUNNER_BACKEND != "docker":
        return False

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
        if RUNNER_BACKEND == "judge0":
            return _run_isolated_judge0(language, code, tests, time_limit_sec)
        if RUNNER_BACKEND != "docker":
            raise RunnerUnavailable("The configured code runner backend is unsupported.")
        return _run_isolated_container(language, code, tests, time_limit_sec)
    finally:
        RUNNER_SLOTS.release()


def _judge0_request(path, query=None, data=None, timeout=10):
    if not runner_available():
        raise RunnerUnavailable("Judge0 is not configured with a valid HTTPS URL and API key.")

    url = f"{JUDGE0_API_URL}/{path.lstrip('/')}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    headers = {
        "Accept": "application/json",
        "X-RapidAPI-Key": JUDGE0_API_KEY,
        "X-RapidAPI-Host": JUDGE0_API_HOST,
    }
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data, separators=(",", ":")).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw_response = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as error:
        messages = {
            401: "Judge0 rejected the API key.",
            403: "Judge0 denied the API request; check your plan and API permissions.",
            429: "Judge0 rate limit reached. Please try again later.",
        }
        message = messages.get(error.code, f"Judge0 request failed with HTTP {error.code}.")
        raise RunnerUnavailable(message) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RunnerUnavailable("Could not reach the Judge0 code execution service.") from error

    if len(raw_response) > MAX_RESPONSE_BYTES:
        raise RunnerUnavailable("Judge0 returned an oversized response.")
    try:
        return json.loads(raw_response)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise RunnerUnavailable("Judge0 returned an invalid response.") from error


def _judge0_language_id(language):
    languages = _judge0_languages()
    if language not in languages:
        raise ValueError("This language is not available from the configured Judge0 service")
    return languages[language]


@lru_cache(maxsize=1)
def _judge0_languages():
    response = _judge0_request("languages", timeout=10)
    if not isinstance(response, list):
        raise RunnerUnavailable("Judge0 returned an invalid language list.")

    language_prefixes = {
        "python3": "Python (3.",
        "c": "C (GCC ",
        "cpp": "C++ (GCC ",
        "java": "Java (",
    }
    result = {}
    for language, prefix in language_prefixes.items():
        candidates = [
            item for item in response
            if isinstance(item, dict)
            and isinstance(item.get("id"), int)
            and isinstance(item.get("name"), str)
            and item["name"].startswith(prefix)
        ]
        if candidates:
            candidates.sort(
                key=lambda item: tuple(
                    int(part) for part in re.findall(r"\d+", item["name"])
                ),
                reverse=True,
            )
            result[language] = candidates[0]["id"]
    return result


def _decode_judge0_output(value):
    if value is None:
        return ""
    if not isinstance(value, str):
        raise RunnerUnavailable("Judge0 returned an invalid output field.")
    try:
        return base64.b64decode(value, validate=True).decode("utf-8", "replace")
    except (ValueError, base64.binascii.Error) as error:
        raise RunnerUnavailable("Judge0 returned an invalid encoded output.") from error


def _judge0_result(item):
    if not isinstance(item, dict):
        raise RunnerUnavailable("Judge0 returned an invalid submission result.")
    status = item.get("status")
    status_id = item.get("status_id")
    if status_id is None and isinstance(status, dict):
        status_id = status.get("id")
    if status_id in (None, 1, 2):
        return None

    compile_output = _decode_judge0_output(item.get("compile_output"))
    if status_id == 6 or compile_output:
        return {
            "compile_error": compile_output or "Compilation failed.",
            "result": None,
        }

    stdout = _decode_judge0_output(item.get("stdout"))
    stderr = _decode_judge0_output(item.get("stderr"))
    timed_out = status_id == 5
    return {
        "compile_error": None,
        "result": {
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": timed_out,
            "returncode": 0 if status_id == 3 else (None if timed_out else 1),
        },
    }


def _run_isolated_judge0(language, code, tests, time_limit_sec):
    language_id = _judge0_language_id(language)
    cpu_limit = max(1.0, min(float(time_limit_sec or 2), 15.0))
    encoded_code = base64.b64encode(code.encode("utf-8")).decode("ascii")
    deadline = time.monotonic() + JUDGE0_TOTAL_TIMEOUT_SEC
    results = []

    for offset in range(0, len(tests), MAX_JUDGE0_BATCH_SIZE):
        batch = tests[offset:offset + MAX_JUDGE0_BATCH_SIZE]
        submissions = [
            {
                "language_id": language_id,
                "source_code": encoded_code,
                "stdin": base64.b64encode(test.get("input", "").encode("utf-8")).decode("ascii"),
                "cpu_time_limit": cpu_limit,
                "wall_time_limit": min(30.0, max(10.0, cpu_limit + 5.0)),
                "memory_limit": 262144,
            }
            for test in batch
        ]
        created = _judge0_request(
            "submissions/batch",
            query={"base64_encoded": "true"},
            data={"submissions": submissions},
            timeout=min(10, max(1, deadline - time.monotonic())),
        )
        if not isinstance(created, list) or len(created) != len(batch):
            raise RunnerUnavailable("Judge0 returned an invalid batch response.")
        tokens = [item.get("token") for item in created if isinstance(item, dict)]
        if len(tokens) != len(batch) or any(not isinstance(token, str) or not token for token in tokens):
            raise RunnerUnavailable("Judge0 could not accept all submissions in this batch.")

        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise RunnerUnavailable("Judge0 did not finish grading before the request timed out.")
            response = _judge0_request(
                "submissions/batch",
                query={
                    "tokens": ",".join(tokens),
                    "base64_encoded": "true",
                    "fields": "token,stdout,stderr,compile_output,status,status_id",
                },
                timeout=min(10, max(1, remaining)),
            )
            items = response.get("submissions") if isinstance(response, dict) else response
            if not isinstance(items, list) or len(items) != len(batch):
                raise RunnerUnavailable("Judge0 returned an invalid batch status response.")
            items_by_token = {
                item.get("token"): item for item in items if isinstance(item, dict)
            }
            if any(token not in items_by_token for token in tokens):
                raise RunnerUnavailable("Judge0 returned results for unexpected submissions.")
            normalized = [_judge0_result(items_by_token[token]) for token in tokens]
            if all(item is not None for item in normalized):
                compile_error = next(
                    (item["compile_error"] for item in normalized if item["compile_error"]),
                    None,
                )
                if compile_error:
                    return {"compile_error": compile_error, "results": []}
                results.extend(item["result"] for item in normalized)
                break
            time.sleep(min(0.75, max(0, deadline - time.monotonic())))

    return {"compile_error": None, "results": results}


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
