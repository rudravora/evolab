"""Backend job policy (app/policy.py) mirrors the worker's verdicts and validates payloads."""

import pytest

from app.policy import classify
from app.scrub import scrub


@pytest.mark.parametrize("job_type,payload,kind", [
    ("shell", {"argv": ["ls", "-la"], "cwd": "code"}, "auto"),
    ("shell", {"argv": ["python", "train.py"], "cwd": "code"}, "auto"),
    ("python_script", {"argv": ["python", "train.py", "--seed", "0"], "cwd": "code"}, "auto"),
    ("pip_install", {"packages": ["numpy==2.1.0", "torch==2.5.1"]}, "auto"),
    ("download", {"url": "https://github.com/x/y.zip", "dest": "data/y.zip"}, "auto"),
    ("git", {"op": "commit", "args": {"message": "patch"}}, "auto"),
    ("git", {"op": "diff", "args": {"paths": ["code/a.py"]}}, "auto"),
    ("write_file", {"path": "m1/a.py", "content": "print(1)"}, "auto"),
    ("list_dir", {"path": "."}, "auto"),
    # needs approval
    ("pip_install", {"packages": ["pykan==0.2.8"]}, "approval"),
    ("download", {"url": "https://example.org/data.csv", "dest": "data.csv"}, "approval"),
    ("shell", {"argv": ["rm", "-rf", "build"], "cwd": "."}, "approval"),
    ("shell", {"argv": ["make"], "cwd": "."}, "approval"),
    # denied
    ("shell", {"argv": ["sudo", "ls"]}, "deny"),
    ("shell", {"argv": ["bash", "-c", "ls"]}, "deny"),
    ("shell", {"argv": ["curl", "https://x"]}, "deny"),
    ("shell", {"argv": "ls -la"}, "deny"),
    ("shell", {"argv": ["cat", "~/.ssh/id_rsa"]}, "deny"),
    ("shell", {"argv": ["python", "-c", "import subprocess"]}, "deny"),
    ("shell", {"argv": ["ls"], "cwd": "/etc"}, "deny"),
    ("shell", {"argv": ["ls"], "cwd": "C:\\Users"}, "deny"),
    ("shell", {"argv": ["ls"], "cwd": "../other_project"}, "deny"),
    ("shell", {"argv": ["ls"], "env": {"OPENAI_API_KEY": "x"}}, "deny"),
    ("python_script", {"argv": ["python", "../escape.py"]}, "deny"),
    ("python_script", {"argv": ["node", "x.js"]}, "deny"),
    ("pip_install", {"packages": ["numpy"]}, "deny"),
    ("pip_install", {"packages": ["numpy>=1.0"]}, "deny"),
    ("git", {"op": "push", "args": {}}, "deny"),
    ("download", {"url": "http://github.com/x", "dest": "x"}, "deny"),
    ("write_file", {"path": "/tmp/x", "content": ""}, "deny"),
    ("rm_rf", {}, "deny"),
])
def test_classify(job_type, payload, kind):
    assert classify(job_type, payload, 300).kind == kind


def test_long_timeout_needs_expensive_run_approval():
    v = classify("python_script", {"argv": ["python", "train.py"]}, 3600)
    assert (v.kind, v.approval_type) == ("approval", "expensive_run")


def test_scrub_keeps_ordinary_text():
    assert scrub("epoch 40 loss 0.0031") == "epoch 40 loss 0.0031"
    assert "sk-" not in scrub("key sk-ABCDEFGHIJKLMNOPQRSTUVWX")
