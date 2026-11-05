"""The installation plan: an ordered list of Steps that follows the Arch Linux installation guide.
Pure data. Building a plan runs nothing and the password never appears in it."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .disks import part_path
from .settings import KEYMAPS, InstallSettings

TARGET = "/mnt"
REPO_DIR = "/opt/chudos-repo"
ESP_SIZE = "+1G"

# Services enabled in the installed system. The boot-update unit is best effort (tolerated if missing).
SERVICES = ("NetworkManager.service", "sddm.service", "systemd-timesyncd.service")


@dataclass(frozen=True)
class Step:
    title: str
    kind: str = "cmd"                 # cmd | write | capture
    argv: tuple[str, ...] = ()
    chroot: bool = False              # run inside the new system via arch-chroot
    stdin_fmt: str = ""               # e.g. "{username}:{password}\n" - filled in at run time, never stored
    path: str = ""                    # write: absolute path INSIDE the target
    content: str = ""                 # write: $vars are filled from captured values
    mode: int = 0o644
    var: str = ""                     # capture: variable name
    destructive: bool = False
    tolerate_failure: bool = False


def pacman_conf() -> str:
    """pacman.conf used ONLY by pacstrap. core/extra verified; the bundled local repo is the single relaxed-signature source."""
    return f"""[options]
HoldPkg = pacman glibc
Architecture = auto
ParallelDownloads = 5
SigLevel = Required DatabaseOptional
LocalFileSigLevel = Optional

[core]
Include = /etc/pacman.d/mirrorlist

[extra]
Include = /etc/pacman.d/mirrorlist

[chudos]
SigLevel = Optional TrustAll
Server = file://{REPO_DIR}
"""


def loader_conf() -> str:
    return "default chudos.conf\ntimeout 3\nconsole-mode max\neditor no\n"


def loader_entry(root_uuid_var: str = "$root_uuid") -> str:
    # Both microcode images exist (amd-ucode and intel-ucode are installed); the CPU loads the one that matches.
    return ("title   ChudOS\nlinux   /vmlinuz-linux\ninitrd  /amd-ucode.img\ninitrd  /intel-ucode.img\n"
            f"initrd  /initramfs-linux.img\noptions root=UUID={root_uuid_var} rw\n")


def build_plan(s: InstallSettings, packages: list[str]) -> list[Step]:
    root_part, esp_part = part_path(s.disk, 2), part_path(s.disk, 1)
    kb = KEYMAPS[s.keymap]
    steps: list[Step] = [
        Step("Erasing the disk", argv=("wipefs", "--all", "--force", s.disk), destructive=True),
        Step("Creating partitions", argv=("sgdisk", "--zap-all", s.disk), destructive=True),
        Step("Creating partitions", argv=("sgdisk", "--clear", "--new=1:0:" + ESP_SIZE, "--typecode=1:ef00", "--change-name=1:ESP",
                                          "--new=2:0:0", "--typecode=2:8300", "--change-name=2:ChudOS", s.disk), destructive=True),
        Step("Waiting for the new partitions", argv=("partprobe", s.disk)),
        Step("Waiting for the new partitions", argv=("udevadm", "settle", "--timeout=30")),
        Step("Formatting the boot partition", argv=("mkfs.fat", "-F", "32", "-n", "ESP", esp_part), destructive=True),
        Step("Formatting the system partition", argv=("mkfs.ext4", "-F", "-L", "chudos", root_part), destructive=True),
        Step("Mounting the new system", argv=("mount", root_part, TARGET)),
        Step("Mounting the new system", argv=("mkdir", "-p", f"{TARGET}/boot")),
        Step("Mounting the new system", argv=("mount", "-o", "umask=0077", esp_part, f"{TARGET}/boot")),
        Step("Reading the disk identifier", kind="capture", argv=("blkid", "-s", "UUID", "-o", "value", root_part), var="root_uuid"),
        Step("Installing ChudOS (this is the long step: it downloads packages)",
             argv=("pacstrap", "-C", "@PACMAN_CONF@", "-K", TARGET, *packages)),
        Step("Recording the disk layout", kind="capture", argv=("genfstab", "-U", TARGET), var="fstab"),
        Step("Recording the disk layout", kind="write", path="/etc/fstab", content="$fstab"),
        Step("Setting the time zone", chroot=True, argv=("ln", "-sf", f"/usr/share/zoneinfo/{s.timezone}", "/etc/localtime")),
        Step("Setting the clock", chroot=True, argv=("hwclock", "--systohc"), tolerate_failure=True),
        Step("Setting the language", kind="write", path="/etc/locale.gen", content=f"{s.locale} UTF-8\nen_US.UTF-8 UTF-8\n"),
        Step("Setting the language", chroot=True, argv=("locale-gen",)),
        Step("Setting the language", kind="write", path="/etc/locale.conf", content=f"LANG={s.locale}\n"),
        Step("Setting the keyboard", kind="write", path="/etc/vconsole.conf", content=f"KEYMAP={kb[1]}\n"),
        Step("Setting the keyboard", kind="write", path="/etc/X11/xorg.conf.d/00-keyboard.conf",
             content=('Section "InputClass"\n    Identifier "system-keyboard"\n    MatchIsKeyboard "on"\n'
                      f'    Option "XkbLayout" "{kb[2]}"\n' + (f'    Option "XkbVariant" "{kb[3]}"\n' if kb[3] else "") + 'EndSection\n')),
        Step("Naming the computer", kind="write", path="/etc/hostname", content=f"{s.hostname}\n"),
        Step("Naming the computer", kind="write", path="/etc/hosts",
             content=f"127.0.0.1 localhost\n::1 localhost\n127.0.1.1 {s.hostname}.localdomain {s.hostname}\n"),
        Step("Creating your account", chroot=True, argv=("useradd", "-m", "-G", "wheel", "-s", "/bin/bash", "-c", s.fullname, s.username)),
        Step("Setting your password", chroot=True, argv=("chpasswd",), stdin_fmt="{username}:{password}\n"),
        Step("Locking the root login (use sudo)", chroot=True, argv=("passwd", "-l", "root")),
        Step("Allowing administrators to use sudo", kind="write", path="/etc/sudoers.d/10-wheel", content="%wheel ALL=(ALL:ALL) ALL\n", mode=0o440),
        Step("Checking the sudo configuration", chroot=True, argv=("visudo", "-c", "-f", "/etc/sudoers.d/10-wheel")),
        Step("Setting up compressed memory (zram)", kind="write", path="/etc/systemd/zram-generator.conf",
             content="[zram0]\nzram-size = min(ram / 2, 4096)\ncompression-algorithm = zstd\n"),
        Step("Turning on system services", chroot=True, argv=("systemctl", "enable", *SERVICES)),
        Step("Turning on boot loader updates", chroot=True, argv=("systemctl", "enable", "systemd-boot-update.service"), tolerate_failure=True),
        Step("Installing the boot loader", chroot=True, argv=("bootctl", "install", "--esp-path=/boot")),
        Step("Configuring the boot loader", kind="write", path="/boot/loader/loader.conf", content=loader_conf()),
        Step("Configuring the boot loader", kind="write", path="/boot/loader/entries/chudos.conf", content=loader_entry()),
        Step("Finishing up", argv=("sync",)),
    ]
    return steps


def describe(steps: list[Step]) -> list[str]:
    """Human-readable plan for --dry-run and the summary screen. No secrets (they are not in the plan)."""
    out = []
    for i, st in enumerate(steps, 1):
        if st.kind == "write":
            what = f"write {st.path}"
        else:
            what = ("[in new system] " if st.chroot else "") + " ".join(st.argv)
        out.append(f"{i:2d}. {st.title}{'  (ERASES DATA)' if st.destructive else ''}\n      {what}")
    return out


def read_package_list(path: Path) -> list[str]:
    from .settings import validate_package_name
    pk = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            if not validate_package_name(line):
                raise ValueError(f"invalid package name in list: {line!r}")
            pk.append(line)
    if not pk:
        raise ValueError("package list is empty")
    return pk
