from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal, Protocol


class SandboxPolicyError(RuntimeError):
    pass


class SandboxTimeout(TimeoutError):
    pass


class SandboxOutOfMemory(MemoryError):
    pass


@dataclass(frozen=True)
class ExecutorSpec:
    executor_id: str
    binary: str
    pinned_version: str
    allowed_arguments: tuple[str, ...]
    network_disabled: bool = True


EXECUTOR_REGISTRY: dict[str, ExecutorSpec] = {
    "poppler": ExecutorSpec(
        executor_id="poppler",
        binary="pdftoppm",
        pinned_version="25.06.0",
        allowed_arguments=("-png", "-r", "150", "INPUT", "OUTPUT"),
    ),
    "ghostscript": ExecutorSpec(
        executor_id="ghostscript",
        binary="gs",
        pinned_version="10.05.1",
        allowed_arguments=("-dSAFER", "-dBATCH", "-dNOPAUSE", "-sDEVICE=pdfwrite"),
    ),
    "tesseract": ExecutorSpec(
        executor_id="tesseract",
        binary="tesseract",
        pinned_version="5.5.1",
        allowed_arguments=("INPUT", "stdout", "-l", "eng", "--psm", "6"),
    ),
}


@dataclass(frozen=True)
class SandboxLimits:
    timeout_seconds: float = 30.0
    memory_bytes: int = 512 * 1024 * 1024
    max_output_bytes: int = 128 * 1024 * 1024
    network_enabled: bool = False


@dataclass(frozen=True)
class ProcessResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    elapsed_seconds: float
    peak_memory_bytes: int
    network_attempted: bool = False


class ProcessRunner(Protocol):
    def __call__(
        self,
        command: tuple[str, ...],
        *,
        input_bytes: bytes,
        limits: SandboxLimits,
    ) -> ProcessResult: ...


VersionProbe = Callable[[str], str]


@dataclass(frozen=True)
class ExecutorReceipt:
    executor_id: str
    binary: str
    pinned_version: str
    observed_version: str
    version_verified: bool
    command_sha256: str
    input_sha256: str
    output_sha256: str
    status: Literal["success", "timeout", "oom", "policy_error", "process_error"]
    returncode: int | None
    elapsed_seconds: float
    peak_memory_bytes: int
    timeout_seconds: float
    memory_limit_bytes: int
    output_limit_bytes: int
    network_disabled: bool
    stderr_sha256: str


class DocumentSandbox:
    def __init__(
        self,
        runner: ProcessRunner,
        limits: SandboxLimits | None = None,
        *,
        version_probe: VersionProbe,
    ) -> None:
        self.runner = runner
        self.limits = limits or SandboxLimits()
        self.version_probe = version_probe
        self.receipts: list[ExecutorReceipt] = []

    def _validate(self, spec: ExecutorSpec, arguments: tuple[str, ...]) -> str:
        if self.limits.network_enabled or not spec.network_disabled:
            raise SandboxPolicyError("document sandbox must run with networking disabled")
        if arguments != spec.allowed_arguments:
            raise SandboxPolicyError(
                f"{spec.executor_id} arguments do not match the pinned allowlist"
            )
        forbidden = {"--enable-network", "http://", "https://", "ftp://"}
        joined = " ".join(arguments).lower()
        if any(token in joined for token in forbidden):
            raise SandboxPolicyError("network-bearing executor argument rejected")
        if (
            self.limits.timeout_seconds <= 0
            or self.limits.memory_bytes <= 0
            or self.limits.max_output_bytes <= 0
        ):
            raise SandboxPolicyError("sandbox limits must be positive")
        observed = self.version_probe(spec.binary).strip()
        if observed != spec.pinned_version:
            raise SandboxPolicyError(
                f"{spec.executor_id} version mismatch: expected {spec.pinned_version}, "
                f"observed {observed or 'unknown'}"
            )
        return observed

    def execute(
        self,
        executor_id: str,
        input_bytes: bytes,
        arguments: tuple[str, ...] = (),
    ) -> tuple[bytes, ExecutorReceipt]:
        try:
            spec = EXECUTOR_REGISTRY[executor_id]
        except KeyError as exc:
            raise SandboxPolicyError(f"unknown executor: {executor_id}") from exc

        observed_version = ""
        command = (spec.binary, *arguments)
        command_sha256 = hashlib.sha256("\0".join(command).encode()).hexdigest()
        input_sha256 = hashlib.sha256(input_bytes).hexdigest()
        status: Literal["success", "timeout", "oom", "policy_error", "process_error"]
        result: ProcessResult | None = None
        output = b""
        try:
            observed_version = self._validate(spec, arguments)
            result = self.runner(command, input_bytes=input_bytes, limits=self.limits)
            if result.network_attempted:
                raise SandboxPolicyError("executor attempted network access")
            if result.elapsed_seconds > self.limits.timeout_seconds:
                raise SandboxTimeout("executor exceeded timeout")
            if result.peak_memory_bytes > self.limits.memory_bytes:
                raise SandboxOutOfMemory("executor exceeded memory limit")
            if len(result.stdout) > self.limits.max_output_bytes:
                raise SandboxPolicyError("executor output exceeds size limit")
            if result.returncode != 0:
                status = "process_error"
            else:
                status = "success"
                output = result.stdout
        except SandboxTimeout:
            status = "timeout"
        except SandboxOutOfMemory:
            status = "oom"
        except SandboxPolicyError:
            status = "policy_error"

        receipt = ExecutorReceipt(
            executor_id=spec.executor_id,
            binary=spec.binary,
            pinned_version=spec.pinned_version,
            observed_version=observed_version,
            version_verified=observed_version == spec.pinned_version,
            command_sha256=command_sha256,
            input_sha256=input_sha256,
            output_sha256=hashlib.sha256(output).hexdigest(),
            status=status,
            returncode=result.returncode if result else None,
            elapsed_seconds=result.elapsed_seconds if result else 0.0,
            peak_memory_bytes=result.peak_memory_bytes if result else 0,
            timeout_seconds=self.limits.timeout_seconds,
            memory_limit_bytes=self.limits.memory_bytes,
            output_limit_bytes=self.limits.max_output_bytes,
            network_disabled=True,
            stderr_sha256=hashlib.sha256(result.stderr if result else b"").hexdigest(),
        )
        self.receipts.append(receipt)
        if status == "timeout":
            raise SandboxTimeout("executor timed out")
        if status == "oom":
            raise SandboxOutOfMemory("executor exceeded memory limit")
        if status == "policy_error":
            raise SandboxPolicyError("executor violated sandbox policy")
        if status == "process_error":
            raise RuntimeError("executor returned non-zero status")
        return output, receipt

    def write_receipts(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "".join(
                json.dumps(asdict(receipt), sort_keys=True) + "\n"
                for receipt in self.receipts
            )
        )


def render_pdf_pages(
    sandbox: DocumentSandbox,
    pdf: bytes,
) -> tuple[bytes, ExecutorReceipt]:
    return sandbox.execute(
        "poppler",
        pdf,
        EXECUTOR_REGISTRY["poppler"].allowed_arguments,
    )


def repair_pdf(
    sandbox: DocumentSandbox,
    pdf: bytes,
) -> tuple[bytes, ExecutorReceipt]:
    return sandbox.execute(
        "ghostscript",
        pdf,
        EXECUTOR_REGISTRY["ghostscript"].allowed_arguments,
    )


def ocr_page(
    sandbox: DocumentSandbox,
    image: bytes,
) -> tuple[str, float, ExecutorReceipt]:
    output, receipt = sandbox.execute(
        "tesseract",
        image,
        EXECUTOR_REGISTRY["tesseract"].allowed_arguments,
    )
    text = output.decode("utf-8", errors="replace").strip()
    confidence = min(1.0, len(text) / 200.0)
    return text, confidence, receipt
