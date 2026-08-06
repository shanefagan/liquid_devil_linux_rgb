#!/usr/bin/env python3
"""Pure Python Debian (.deb) Package Builder for liquid-devil-rgb.

Assembles a valid .deb package file directly using Python standard library (tarfile, lzma).
"""

import io
import os
import tarfile

def create_ar_archive(members: list[tuple[str, bytes]]) -> bytes:
    """Create a standard Unix ar archive containing (filename, data) tuples."""
    buf = bytearray(b"!<arch>\n")
    for name, data in members:
        hdr = f"{name:<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(data):<10}`\n".encode("latin1")
        buf += hdr
        buf += data
        if len(data) % 2 != 0:
            buf += b"\n"
    return bytes(buf)

def main():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    out_dir = os.path.join(repo_root, "dist")
    os.makedirs(out_dir, exist_ok=True)
    deb_path = os.path.join(out_dir, "liquid-devil-rgb_1.0.0-1_all.deb")

    debian_binary = b"2.0\n"

    control_content = """Package: liquid-devil-rgb
Version: 1.0.0-1
Section: utils
Priority: optional
Architecture: all
Maintainer: Shane Fagan <shane@performativenonsense.com>
Depends: python3, i2c-tools
Description: Linux I2C RGB Control for PowerColor Radeon RX 7900 XTX Liquid Devil
 Reverse-engineered hardware protocol implementation for the V2 I2C RGB
 controller (0x22). Includes OpenRGB SDK sync client for real-time PC lighting.
""".encode("utf-8")

    control_buf = io.BytesIO()
    with tarfile.open(fileobj=control_buf, mode="w:xz") as tar:
        ti = tarfile.TarInfo("control")
        ti.size = len(control_content)
        ti.mode = 0o644
        tar.addfile(ti, io.BytesIO(control_content))

    control_tar_xz = control_buf.getvalue()

    data_buf = io.BytesIO()
    with tarfile.open(fileobj=data_buf, mode="w:xz") as tar:
        cli_launcher = """#!/usr/bin/env python3
from liquid_devil_rgb.cli import main
if __name__ == '__main__':
    main()
""".encode("utf-8")
        
        ti = tarfile.TarInfo("./usr/bin/liquid-devil-rgb")
        ti.size = len(cli_launcher)
        ti.mode = 0o755
        tar.addfile(ti, io.BytesIO(cli_launcher))

        pkg_src_dir = os.path.join(repo_root, "src", "liquid_devil_rgb")
        for fname in os.listdir(pkg_src_dir):
            fpath = os.path.join(pkg_src_dir, fname)
            if os.path.isfile(fpath) and fname.endswith(".py"):
                with open(fpath, "rb") as f:
                    content = f.read()
                ti = tarfile.TarInfo(f"./usr/lib/python3/dist-packages/liquid_devil_rgb/{fname}")
                ti.size = len(content)
                ti.mode = 0o644
                tar.addfile(ti, io.BytesIO(content))

        # Systemd service unit
        svc_path = os.path.join(repo_root, "systemd", "liquid-devil-sync.service")
        if os.path.exists(svc_path):
            with open(svc_path, "rb") as f:
                content = f.read()
            ti = tarfile.TarInfo("./lib/systemd/system/liquid-devil-sync.service")
            ti.size = len(content)
            ti.mode = 0o644
            tar.addfile(ti, io.BytesIO(content))

        # Docs
        for docname in ["README.md", "PROTOCOL.md"]:
            docpath = os.path.join(repo_root, docname)
            if os.path.exists(docpath):
                with open(docpath, "rb") as f:
                    content = f.read()
                ti = tarfile.TarInfo(f"./usr/share/doc/liquid-devil-rgb/{docname}")
                ti.size = len(content)
                ti.mode = 0o644
                tar.addfile(ti, io.BytesIO(content))

    data_tar_xz = data_buf.getvalue()

    deb_bytes = create_ar_archive([
        ("debian-binary", debian_binary),
        ("control.tar.xz", control_tar_xz),
        ("data.tar.xz", data_tar_xz),
    ])

    with open(deb_path, "wb") as f:
        f.write(deb_bytes)

    print(f"Built Debian package: {deb_path}")

if __name__ == "__main__":
    main()
