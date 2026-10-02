"""Install the small set of FreeSurfer/SUMA files used by the pipeline."""

import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import tarfile
import tempfile
from urllib.request import urlopen


_BUNDLE = Path(__file__).parent / "data" / "reference_bundle.tar.gz"
_SHA256 = "002645b2898ba81fbb0c208c766d8d3f0bd71354b942a18c44bb3bc6e310ef5d"
_REQUIRED = (
    "fsaverage/surf/lh.sphere.reg",
    "fsaverage/surf/rh.sphere.reg",
    "MNI152NLin6Asym/surf/lh.sphere.reg",
    "MNI152NLin6Asym/surf/rh.sphere.reg",
    "MNI152NLin6Asym/SUMA/std.141.MNI152NLin6Asym_lh.niml.M2M",
    "MNI152NLin6Asym/SUMA/std.141.MNI152NLin6Asym_rh.niml.M2M",
    "MNI152NLin6Asym/SUMA/std.141.lh.smoothwm.gii",
    "MNI152NLin6Asym/SUMA/std.141.rh.smoothwm.gii",
    "MNI152NLin6Asym/SUMA/std.141.lh.pial.gii",
    "MNI152NLin6Asym/SUMA/std.141.rh.pial.gii",
    "MNI152NLin6Asym/SUMA/lh.ribbon.nii.gz",
    "MNI152NLin6Asym/SUMA/rh.ribbon.nii.gz",
)


def _valid(root: Path) -> bool:
    return all((root / relative).is_file() and (root / relative).stat().st_size for relative in _REQUIRED)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_reference_files(
    cache_dir: str | os.PathLike | None = None,
    download_url: str | None = None,
) -> Path:
    """Return a subjects directory containing the required reference assets.

    The bundled archive is used by default. Set ``SURF2VOLUME_REF_URL`` or
    pass ``download_url`` to fetch the same checksum-pinned archive from a host.
    """
    if cache_dir is None:
        cache_dir = Path.home() / ".cache" / "surf2volume" / "references-v1"
    root = Path(cache_dir).expanduser().resolve()
    if _valid(root):
        return root

    root.parent.mkdir(parents=True, exist_ok=True)
    url = download_url or os.environ.get("SURF2VOLUME_REF_URL")
    with tempfile.TemporaryDirectory(prefix="surf2volume-ref-", dir=root.parent) as temp:
        temp = Path(temp)
        archive = temp / "reference_bundle.tar.gz"
        if url:
            with urlopen(url, timeout=60) as response, archive.open("wb") as output:
                shutil.copyfileobj(response, output)
        elif _BUNDLE.is_file():
            shutil.copyfile(_BUNDLE, archive)
        else:
            raise FileNotFoundError(
                "Reference bundle is missing. Install the complete surf2volume-ref "
                "package or set SURF2VOLUME_REF_URL to its hosted archive."
            )

        if _sha256(archive) != _SHA256:
            raise ValueError("Reference bundle SHA-256 mismatch; refusing to extract it")

        staging = temp / "subjects"
        staging.mkdir()
        with tarfile.open(archive, "r:gz") as bundle:
            members = bundle.getmembers()
            for member in members:
                member_path = PurePosixPath(member.name)
                if member_path.is_absolute() or ".." in member_path.parts or not member.isfile():
                    raise ValueError(f"Unsafe or unexpected reference archive member: {member.name}")
            bundle.extractall(staging, members=members)
        if not _valid(staging):
            raise ValueError("Reference archive is incomplete; required files are missing")

        if root.exists():
            shutil.rmtree(root)
        staging.replace(root)

    print(f"Reference files ready in: {root}")
    return root
