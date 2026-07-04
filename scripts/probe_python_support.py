"""Deep functional probes for Python-version support (issue #882).

Goes beyond install + smoke-import: each probe exercises the runtime path
that wheel metadata cannot prove — C extensions loading, removed-stdlib
shims (audioop on 3.13+), sdist-built Cython modules (imagededup on 3.13+),
native event backends (watchdog fsevents/inotify), and small end-to-end
round-trips through the scientific/media stack.

Run inside an environment installed with the risky extras:
    pip install -e ".[dev,audio,video,dedup,scientific,search,archive,parsers,cad,build,llama]"
(plus mlx on Darwin). Exits 0 when every applicable probe passes, 1 otherwise.
"""

from __future__ import annotations

import platform
import sys
import tempfile
import threading
import traceback
from collections.abc import Callable
from pathlib import Path

IS_DARWIN = platform.system() == "Darwin"


def require(condition: bool, message: str) -> None:
    """Raise AssertionError for failed probe invariants, even under python -O."""
    if not condition:
        raise AssertionError(message)


def probe_numpy() -> str:
    import numpy as np

    arr = np.asarray([0.3, 0.1, 0.2], dtype=np.float64)
    require(list(np.argsort(arr)) == [1, 2, 0], "numpy argsort result mismatch")
    # NEP 50: scalar promotion must not upcast float32 arrays (numpy 2 behavior)
    require(
        (np.zeros(2, dtype=np.float32) + 1.0).dtype == np.float32,
        "numpy scalar promotion unexpectedly upcast float32",
    )
    return f"numpy {np.__version__}"


def probe_pydub() -> str:
    # Exercises stdlib `audioop` — removed in 3.13, restored by audioop-lts.
    from pydub import AudioSegment

    seg = AudioSegment.silent(duration=50)
    require(seg.rms == 0, "pydub silent segment RMS expected to be 0")
    require(seg.set_channels(2).channels == 2, "pydub channel conversion failed")
    return "pydub silent-segment RMS via audioop OK"


def probe_imagededup() -> str:
    import numpy as np
    from imagededup.methods import PHash
    from PIL import Image

    rng = np.random.default_rng(0)
    with tempfile.TemporaryDirectory() as d:
        for name in ("a.png", "b.png"):
            arr = rng.integers(0, 255, (64, 64, 3), dtype=np.uint8)
            Image.fromarray(arr, "RGB").save(Path(d) / name)
        hashes = PHash().encode_images(d)
    require(len(hashes) == 2, "imagededup expected hashes for both probe images")
    # Prove the compiled extension exists (sdist-built on 3.13+):
    from imagededup.handlers.search.brute_force_cython import (  # noqa: F401
        BruteForceCython,
    )

    return "imagededup PHash + Cython extension OK"


def probe_watchdog() -> str:
    # Proves the native observer backend (fsevents on macOS is an sdist build
    # on Python 3.14 — no cp314 wheel exists as of watchdog 6.0).
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer

    seen = threading.Event()

    class Handler(FileSystemEventHandler):
        def on_any_event(self, event: object) -> None:
            seen.set()

    with tempfile.TemporaryDirectory() as d:
        observer = Observer()
        observer.schedule(Handler(), d)
        observer.start()
        try:
            (Path(d) / "touch.txt").write_text("x")
            fired = seen.wait(timeout=10)
        finally:
            observer.stop()
            observer.join(timeout=10)
    require(fired, "no filesystem event received within 10s")
    return f"watchdog {type(observer).__name__} event round-trip OK"


def probe_websockets() -> str:
    import websockets

    try:
        import websockets.speedups

        impl = "C-accelerated"
    except ImportError:
        impl = "pure-Python fallback"
    return f"websockets {websockets.__version__} ({impl})"


def probe_torch() -> str:
    import torch

    t = torch.ones(2, 2)
    require((t @ t).sum().item() == 8.0, "torch matmul probe produced unexpected result")
    return f"torch {torch.__version__} matmul OK"


def probe_opencv() -> str:
    import cv2
    import numpy as np

    gray = cv2.cvtColor(np.zeros((8, 8, 3), dtype=np.uint8), cv2.COLOR_RGB2GRAY)
    require(gray.shape == (8, 8), "opencv grayscale conversion produced wrong shape")
    return f"opencv {cv2.__version__} cvtColor OK"


def probe_scipy() -> str:
    import numpy as np
    from scipy.io import loadmat, savemat

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "probe.mat"
        savemat(path, {"x": np.arange(4)})
        loaded = loadmat(path)
    require(
        list(loaded["x"].flatten()) == [0, 1, 2, 3],
        "scipy .mat round-trip values mismatch",
    )
    import scipy

    return f"scipy {scipy.__version__} .mat round-trip OK"


def probe_h5py() -> str:
    import h5py
    import numpy as np

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "probe.h5"
        with h5py.File(path, "w") as f:
            f.create_dataset("x", data=np.arange(4))
        with h5py.File(path, "r") as f:
            require(list(f["x"][:]) == [0, 1, 2, 3], "h5py round-trip values mismatch")
    return f"h5py {h5py.__version__} round-trip OK"


def probe_netcdf4() -> str:
    import netCDF4

    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "probe.nc"
        with netCDF4.Dataset(path, "w") as ds:
            ds.createDimension("t", 3)
            var = ds.createVariable("v", "f8", ("t",))
            var[:] = [1.0, 2.0, 3.0]
        with netCDF4.Dataset(path, "r") as ds:
            require(float(ds["v"][1]) == 2.0, "netCDF4 round-trip values mismatch")
    return f"netCDF4 {netCDF4.__version__} round-trip OK"


def probe_sklearn() -> str:
    import sklearn
    from sklearn.feature_extraction.text import TfidfVectorizer

    matrix = TfidfVectorizer().fit_transform(["alpha beta", "beta gamma"])
    require(matrix.shape == (2, 3), "scikit-learn TF-IDF matrix shape mismatch")
    return f"scikit-learn {sklearn.__version__} TF-IDF OK"


def probe_py7zr() -> str:
    # Exercises the native codec stack (pyppmd/pybcj/pyzstd).
    import py7zr

    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "payload.txt"
        src.write_text("probe payload")
        archive = Path(d) / "probe.7z"
        with py7zr.SevenZipFile(archive, "w") as z:
            z.write(src, "payload.txt")
        with py7zr.SevenZipFile(archive, "r") as z:
            z.extractall(Path(d) / "out")
        require(
            (Path(d) / "out" / "payload.txt").read_text() == "probe payload",
            "py7zr round-trip payload mismatch",
        )
    return f"py7zr {py7zr.__version__} round-trip OK"


def probe_pymupdf() -> str:
    import fitz

    doc = fitz.open()
    doc.new_page()
    require(doc.page_count == 1, "PyMuPDF page creation probe expected page_count == 1")
    return f"PyMuPDF {fitz.VersionBind} page create OK"


def probe_lxml() -> str:
    import lxml.etree as etree

    root = etree.fromstring("<r><c>x</c></r>")
    require(root.findtext("c") == "x", "lxml XML parse probe failed")
    return f"lxml {etree.__version__} parse OK"


def probe_bcrypt() -> str:
    import bcrypt

    hashed = bcrypt.hashpw(b"probe", bcrypt.gensalt(rounds=4))
    require(bcrypt.checkpw(b"probe", hashed), "bcrypt hash/check probe failed")
    return f"bcrypt {bcrypt.__version__} hash/check OK"


def probe_psutil() -> str:
    import psutil

    require(psutil.Process().memory_info().rss > 0, "psutil reported non-positive RSS")
    return f"psutil {psutil.__version__} process info OK"


def probe_faster_whisper() -> str:
    # Importing loads the ctranslate2 native library.
    import ctranslate2
    import faster_whisper  # noqa: F401

    return f"faster-whisper import OK (ctranslate2 {ctranslate2.__version__})"


def probe_llama_cpp() -> str:
    import llama_cpp

    # Native C API call — proves the compiled library loads and answers.
    require(
        isinstance(llama_cpp.llama_supports_mmap(), bool),
        "llama-cpp-python native bool probe failed",
    )
    return f"llama-cpp-python {llama_cpp.__version__} native call OK"


def probe_mlx() -> str:
    import mlx.core as mx

    require((mx.array([1, 2]) + 1).sum().item() == 5, "mlx array operation probe failed")
    return "mlx array op OK"


def probe_ezdxf() -> str:
    import ezdxf

    doc = ezdxf.new()
    doc.modelspace().add_line((0, 0), (1, 1))
    require(len(doc.modelspace()) == 1, "ezdxf entity creation probe failed")
    return f"ezdxf {ezdxf.__version__} entity create OK"


# (name, probe, applicable) — inapplicable probes report SKIP instead of FAIL.
PROBES: list[tuple[str, Callable[[], str], bool]] = [
    ("numpy", probe_numpy, True),
    ("pydub/audioop", probe_pydub, True),
    ("imagededup", probe_imagededup, True),
    ("watchdog", probe_watchdog, True),
    ("websockets", probe_websockets, True),
    ("torch", probe_torch, True),
    ("opencv", probe_opencv, True),
    ("scipy", probe_scipy, True),
    ("h5py", probe_h5py, True),
    ("netCDF4", probe_netcdf4, True),
    ("scikit-learn", probe_sklearn, True),
    ("py7zr", probe_py7zr, True),
    ("PyMuPDF", probe_pymupdf, True),
    ("lxml", probe_lxml, True),
    ("bcrypt", probe_bcrypt, True),
    ("psutil", probe_psutil, True),
    ("faster-whisper", probe_faster_whisper, True),
    ("llama-cpp-python", probe_llama_cpp, True),
    ("mlx", probe_mlx, IS_DARWIN),
    ("ezdxf", probe_ezdxf, True),
]


def main() -> int:
    """Run every applicable probe and print a PASS/FAIL/SKIP table."""
    print(f"Deep probes on Python {sys.version.split()[0]} / {platform.platform()}\n")
    failures = 0
    for name, probe, applicable in PROBES:
        if not applicable:
            print(f"  SKIP  {name:<18} (not applicable on this platform)")
            continue
        try:
            detail = probe()
            print(f"  PASS  {name:<18} {detail}")
        except Exception as exc:  # report every probe's outcome, then fail at the end
            failures += 1
            print(f"  FAIL  {name:<18} {type(exc).__name__}: {exc}")
            traceback.print_exc()
    print(f"\n{failures} failure(s) across {len(PROBES)} probes")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
