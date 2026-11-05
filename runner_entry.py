import json
import os
import resource
import signal
import subprocess
import sys
import tempfile
from pathlib import Path


MAX_REQUEST_BYTES = 2 * 1024 * 1024
MAX_OUTPUT_CHARS = 10000
MAX_FILE_BYTES = 10 * 1024 * 1024
LANGUAGE_COMMANDS = {
    "python3": ("python3", "main.py"),
    "c": ("./main.out",),
    "cpp": ("./main.out",),
    "java": ("java", "-Xmx192m", "-XX:MaxMetaspaceSize=96m", "-cp", ".", "Main"),
}


def _limit_process(cpu_seconds):
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_FILE_BYTES, MAX_FILE_BYTES))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))


def _kill_process_group(process_id):
    try:
        os.killpg(process_id, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _compile(language, source, work_dir):
    filenames = {"python3": "main.py", "c": "main.c", "cpp": "main.cpp", "java": "Main.java"}
    (work_dir / filenames[language]).write_text(source, encoding="utf-8")
    commands = {
        "c": ["gcc", "-O2", "-o", "main.out", "main.c"],
        "cpp": ["g++", "-O2", "-std=c++17", "-o", "main.out", "main.cpp"],
        "java": ["javac", "-J-Xmx192m", "Main.java"],
    }
    if language == "python3":
        return None

    try:
        process = subprocess.Popen(
            commands[language],
            cwd=work_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            preexec_fn=lambda: _limit_process(15),
            start_new_session=True,
        )
        try:
            _, stderr = process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            _kill_process_group(process.pid)
            process.communicate()
            return "Compilation timed out"
        finally:
            _kill_process_group(process.pid)
    except OSError as error:
        return f"Compiler could not start: {error}"

    if process.returncode:
        return (stderr or "Compilation failed")[-4000:]
    return None


def _execute(language, stdin_text, time_limit, work_dir):
    command = LANGUAGE_COMMANDS[language]
    with tempfile.TemporaryFile() as stdout_file, tempfile.TemporaryFile() as stderr_file:
        try:
            process = subprocess.Popen(
                command,
                cwd=work_dir,
                stdin=subprocess.PIPE,
                stdout=stdout_file,
                stderr=stderr_file,
                text=True,
                preexec_fn=lambda: _limit_process(max(1, int(time_limit))),
                start_new_session=True,
            )
        except OSError as error:
            stderr_file.write(f"Runtime error: {error}".encode("utf-8", "replace"))
            process = None

        if process is not None:
            try:
                process.communicate(input=stdin_text, timeout=time_limit)
                timed_out = False
                returncode = process.returncode
            except subprocess.TimeoutExpired:
                _kill_process_group(process.pid)
                process.communicate()
                timed_out = True
                returncode = None
            finally:
                _kill_process_group(process.pid)

        if process is None:
            timed_out = False
            returncode = None

        stdout_file.seek(0)
        stderr_file.seek(0)
        stdout = stdout_file.read(MAX_OUTPUT_CHARS + 1).decode("utf-8", "replace")
        stderr = stderr_file.read(MAX_OUTPUT_CHARS + 1).decode("utf-8", "replace")
        return {
            "stdout": stdout[:MAX_OUTPUT_CHARS],
            "stderr": stderr[:MAX_OUTPUT_CHARS],
            "returncode": returncode,
            "timed_out": timed_out,
        }


def main():
    raw_request = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    if len(raw_request) > MAX_REQUEST_BYTES:
        raise ValueError("Runner request exceeds size limit")

    request = json.loads(raw_request)
    language = request.get("language")
    source = request.get("code")
    tests = request.get("tests")
    if language not in LANGUAGE_COMMANDS or not isinstance(source, str) or not isinstance(tests, list):
        raise ValueError("Invalid runner request")

    with tempfile.TemporaryDirectory(prefix="submission-", dir="/tmp") as directory:
        work_dir = Path(directory)
        compile_error = _compile(language, source, work_dir)
        if compile_error:
            response = {"compile_error": compile_error, "results": []}
        else:
            time_limit = max(1, min(float(request.get("time_limit_sec", 2)), 15))
            results = [
                _execute(language, test.get("input", ""), time_limit, work_dir)
                for test in tests
            ]
            response = {"compile_error": None, "results": results}

    sys.stdout.write(json.dumps(response))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        sys.stderr.write(f"Runner error: {error}\n")
        sys.exit(1)
