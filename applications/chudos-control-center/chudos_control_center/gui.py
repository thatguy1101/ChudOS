"""ChudOS Control Centre (PySide6). UI wiring only; logic is in tools.py, chudos_monitor.sysinfo and
the profiles engine (embedded, not re-implemented)."""
from __future__ import annotations

import sys
from pathlib import Path

from chudos_monitor import maintenance as maint
from chudos_monitor import sysinfo
from chudos_profiles import sound
from chudos_profiles.cli import make_store

from . import tools

SECTIONS = ("Overview", "Appearance", "Dopamine Profiles", "Sound", "Developer", "Gaming", "System")


def fmt(metric, render=str) -> str:
    return render(metric.value) if metric.available else f"unavailable ({metric.reason})"


def build_window(store=None, *, launcher=tools.launch, sound_path: Path | None = None, updates_fn=None,
                 git_run=None, home: Path | None = None, profiles_widget_factory=None, confirm=None, maint_mod=None):
    from PySide6.QtCore import Qt, QRunnable, QObject, QThreadPool, QTimer, Signal
    from PySide6.QtGui import QKeySequence, QShortcut
    from PySide6.QtWidgets import (QCheckBox, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget, QProgressBar,
                                   QMessageBox, QPlainTextEdit, QPushButton, QSlider, QStackedWidget, QVBoxLayout, QWidget)

    store = store or make_store()
    maint_ = maint_mod or maint
    sound_path = sound_path or sound.config_path()
    updates_fn = updates_fn or sysinfo.pending_updates
    run_kw = {"run": git_run} if git_run else {}
    home = home or Path.home()

    class Done(QObject):
        finished = Signal(object)

    class Job(QRunnable):
        def __init__(self, fn):
            super().__init__(); self.fn = fn; self.signals = Done()
        def run(self):
            try:
                self.signals.finished.emit(self.fn())
            except Exception as exc:  # noqa: BLE001 - surfaced to the user
                self.signals.finished.emit(exc)

    def background(fn, cb):
        job = Job(fn); job.signals.finished.connect(cb); win._jobs.append(job); QThreadPool.globalInstance().start(job)

    def label(text="", wrap=True, selectable=False):
        l = QLabel(text); l.setWordWrap(wrap)
        if selectable:
            l.setTextInteractionFlags(Qt.TextSelectableByMouse)
        return l

    def heading(text):
        l = QLabel(text); l.setStyleSheet("font-size: 20px; font-weight: 600;"); return l

    def notice(widget_label, level, text):
        widget_label.setText(text)
        widget_label.setStyleSheet({"ok": "color:#2e8b57;", "warn": "color:#b8860b;", "error": "color:#d9534f;"}[level])

    def action_button(text, argv, status):
        b = QPushButton(text)
        def go():
            ok, msg = launcher(argv)
            notice(status, "ok" if ok else "error", msg)
        b.clicked.connect(go)
        return b

    win = QWidget(); win._jobs = []
    win.setWindowTitle("ChudOS Control Centre"); win.resize(900, 560)
    outer = QHBoxLayout(win)
    nav = QListWidget(); nav.setMaximumWidth(210); nav.setAccessibleName("Sections"); nav.addItems(SECTIONS)
    pages = QStackedWidget()
    outer.addWidget(nav); outer.addWidget(pages, 1)

    def page(title):
        w = QWidget(); lay = QVBoxLayout(w); lay.addWidget(heading(title)); return w, lay

    # ---------------- Overview ----------------
    ov, lay = page("Overview")
    ov_labels = {k: label() for k in ("profile", "os", "kernel", "cpu_model", "uptime", "cpu", "mem_text", "disk_text")}
    mem_bar, disk_bar = QProgressBar(), QProgressBar()
    for b in (mem_bar, disk_bar):
        b.setTextVisible(False); b.setMaximumHeight(10)
    form = QFormLayout(); lay.addLayout(form)
    for key, text in (("profile", "Active profile"), ("os", "System"), ("kernel", "Kernel"), ("cpu_model", "Processor"),
                      ("uptime", "Uptime"), ("cpu", "CPU usage")):
        form.addRow(text, ov_labels[key])
    form.addRow("Memory", ov_labels["mem_text"]); form.addRow("", mem_bar)
    form.addRow("Storage (/)", ov_labels["disk_text"]); form.addRow("", disk_bar)
    ov_labels["updates"] = label("Not checked yet (see System).")
    form.addRow("Updates", ov_labels["updates"])
    lay.addStretch(1)
    sampler = sysinfo.CpuSampler()

    def refresh_overview():
        ov_labels["profile"].setText(store.active() or "none applied yet")
        ver = sysinfo.chudos_version()
        ov_labels["os"].setText(fmt(sysinfo.os_name()) + (f"  ·  ChudOS {ver.value}" if ver.available else "  ·  (ChudOS release file not present)"))
        ov_labels["kernel"].setText(fmt(sysinfo.kernel()))
        ov_labels["cpu_model"].setText(fmt(sysinfo.cpu_model()))
        ov_labels["uptime"].setText(fmt(sysinfo.uptime_seconds(), sysinfo.human_duration))
        ov_labels["cpu"].setText(fmt(sampler.sample(), lambda v: f"{v}%"))
        m = sysinfo.memory()
        if m.available:
            v = m.value
            ov_labels["mem_text"].setText(f"{sysinfo.human_bytes(v['used'])} used of {sysinfo.human_bytes(v['total'])}")
            mem_bar.setRange(0, 1000); mem_bar.setValue(int(1000 * v["used"] / v["total"]))
        else:
            ov_labels["mem_text"].setText(fmt(m)); mem_bar.setValue(0)
        d = sysinfo.storage("/")
        if d.available:
            v = d.value
            ov_labels["disk_text"].setText(f"{sysinfo.human_bytes(v['used'])} used, {sysinfo.human_bytes(v['free'])} free")
            disk_bar.setRange(0, 1000); disk_bar.setValue(int(1000 * v["used"] / v["total"]))
        else:
            ov_labels["disk_text"].setText(fmt(d)); disk_bar.setValue(0)

    timer = QTimer(win); timer.setInterval(2000)
    timer.timeout.connect(lambda: refresh_overview() if win.isActiveWindow() else None)  # no work when in background

    # ---------------- Appearance ----------------
    ap, lay = page("Appearance")
    ap_status = label()
    lay.addWidget(label("Colours, fonts, icons, themes and effects are handled by KDE System Settings. "
                        "Accent colour, animation speed and blur are also set by your Dopamine Profile: "
                        "applying a profile overrides them."))
    for text, page_id in tools.KDE_PAGES.items():
        lay.addWidget(action_button(f"Open {text} settings", tools.kde_settings_argv(page_id), ap_status))
    lay.addWidget(action_button("Open all System Settings", tools.kde_settings_argv(None), ap_status))
    lay.addWidget(ap_status); lay.addStretch(1)

    # ---------------- Profiles (existing engine + window) ----------------
    if profiles_widget_factory is None:
        from chudos_profiles.gui import build_window as build_profiles
        profiles_widget_factory = build_profiles
    prof_widget = profiles_widget_factory(store)

    # ---------------- Sound ----------------
    so, lay = page("Sound")
    cfg = sound.load(sound_path)
    so_enabled = QCheckBox("Play ChudOS decorative sounds"); so_enabled.setChecked(cfg["enabled"])
    so_vol = QSlider(Qt.Horizontal); so_vol.setRange(0, 100); so_vol.setValue(cfg["volume"]); so_vol.setAccessibleName("Effects volume")
    so_vol_label = label(f"{cfg['volume']}%"); so_status = label()
    so_vol.valueChanged.connect(lambda v: so_vol_label.setText(f"{v}%"))
    lay.addWidget(label("These sounds are played by ChudOS itself (currently: when a profile is applied). They never change "
                        "application audio or system notification sounds. Per-category volumes and sound packs are not implemented yet."))
    lay.addWidget(so_enabled)
    row = QHBoxLayout(); row.addWidget(QLabel("Effects volume")); row.addWidget(so_vol, 1); row.addWidget(so_vol_label); lay.addLayout(row)
    prev, save_s = QPushButton("Preview"), QPushButton("Save")
    def preview():
        st = sound.play("profile-applied", {"enabled": True, "volume": so_vol.value()})
        msgs = {"played": ("ok", "Played."), "disabled": ("warn", "Volume is 0."), "no-asset": ("error", "Sound file is not installed."),
                "no-player": ("error", "No audio player found (pw-play or paplay)."), "failed": ("error", "Could not start the player.")}
        notice(so_status, *msgs[st])
    def save_sound():
        try:
            sound.save(sound_path, so_enabled.isChecked(), so_vol.value()); notice(so_status, "ok", "Saved.")
        except (OSError, ValueError) as exc:
            notice(so_status, "error", f"Could not save: {exc}")
    prev.clicked.connect(preview); save_s.clicked.connect(save_sound)
    lay.addWidget(prev); lay.addWidget(save_s); lay.addWidget(so_status); lay.addStretch(1)

    # ---------------- Developer ----------------
    dv, lay = page("Developer")
    dv_status = label()
    tiers = {}
    for t, ok in tools.tool_status(tools.DEV_TOOLS):
        tiers.setdefault(t.tier, []).append((t, ok))
    for tier in (tools.ESSENTIAL, tools.RECOMMENDED, tools.OPTIONAL):
        lay.addWidget(label(f"<b>{tier.title()}</b>"))
        for t, ok in tiers.get(tier, []):
            lay.addWidget(label(f"{'✔' if ok else '✘'} {t.name}" + ("" if ok else f" — not installed (package: {t.package})") + (f"  [{t.note}]" if t.note else "")))
    hint = tools.install_hint([t for t, ok in tools.tool_status(tools.DEV_TOOLS) if not ok and t.tier != tools.OPTIONAL])
    if hint:
        lay.addWidget(label("To install the missing essential/recommended tools, run in a terminal:"))
        lay.addWidget(label(hint, selectable=True))
    pdir = tools.projects_dir(home)
    def open_projects():
        try:
            pdir.mkdir(exist_ok=True)
        except OSError as exc:
            return notice(dv_status, "error", f"Cannot create {pdir}: {exc}")
        ok, msg = launcher(["xdg-open", str(pdir)]); notice(dv_status, "ok" if ok else "error", msg)
    def open_term():
        try:
            pdir.mkdir(exist_ok=True)
        except OSError as exc:
            return notice(dv_status, "error", f"Cannot create {pdir}: {exc}")
        ok, msg = launcher(tools.terminal_argv(pdir)); notice(dv_status, "ok" if ok else "error", msg)
    b1, b2 = QPushButton("Open ~/Projects (created if missing)"), QPushButton("Terminal in ~/Projects")
    b1.clicked.connect(open_projects); b2.clicked.connect(open_term); lay.addWidget(b1); lay.addWidget(b2)
    lay.addWidget(action_button("Arch Wiki (documentation)", ["xdg-open", "https://wiki.archlinux.org/"], dv_status))
    lay.addWidget(label("<b>Git identity</b> (name and email only; ChudOS never stores passwords or tokens)"))
    g_name, g_email = QLineEdit(tools.git_get("user.name", **run_kw) or ""), QLineEdit(tools.git_get("user.email", **run_kw) or "")
    g_name.setAccessibleName("Git name"); g_email.setAccessibleName("Git email")
    gf = QFormLayout(); gf.addRow("Name", g_name); gf.addRow("Email", g_email); lay.addLayout(gf)
    g_save = QPushButton("Save Git identity")
    def save_git():
        ok, msg = tools.git_set_identity(g_name.text(), g_email.text(), **run_kw); notice(dv_status, "ok" if ok else "error", msg)
    g_save.clicked.connect(save_git); lay.addWidget(g_save); lay.addWidget(dv_status); lay.addStretch(1)

    # ---------------- Gaming ----------------
    gm, lay = page("Gaming")
    gm_status = label()
    lay.addWidget(label("ChudOS does not claim that any setting here improves game performance. Steam is proprietary and needs the "
                        "multilib repository enabled; Minecraft itself is not included."))
    gstat = tools.tool_status(tools.GAME_TOOLS)
    for t, ok in gstat:
        lay.addWidget(label(f"{'✔' if ok else '✘'} {t.name}" + ("" if ok else f" — not installed (package: {t.package})") + (f"  [{t.note}]" if t.note else "")))
    gh = tools.install_hint([t for t, ok in gstat if not ok and t.tier == tools.RECOMMENDED])
    if gh:
        lay.addWidget(label("To install the recommended items, run in a terminal:")); lay.addWidget(label(gh, selectable=True))
    for t, ok in gstat:
        if ok and t.binary in ("steam", "prismlauncher"):
            lay.addWidget(action_button(f"Launch {t.name}", [t.binary], gm_status))
    mc = home / "Minecraft-Servers"
    def open_mc():
        try:
            mc.mkdir(exist_ok=True)
        except OSError as exc:
            return notice(gm_status, "error", f"Cannot create {mc}: {exc}")
        ok, msg = launcher(["xdg-open", str(mc)]); notice(gm_status, "ok" if ok else "error", msg)
    b3 = QPushButton("Open ~/Minecraft-Servers (created if missing)"); b3.clicked.connect(open_mc); lay.addWidget(b3)
    lay.addWidget(label("The Gaming profile (Dopamine Profiles) turns off animations and blur and lowers decorative sound volume."))
    lay.addWidget(gm_status); lay.addStretch(1)

    # ---------------- System ----------------
    sy, lay = page("System")
    sy_status = label(); sy_updates = label("Updates have not been checked.")
    disks = label(); lay.addWidget(disks)
    def refresh_disks():
        lines = []
        for p in ("/", "/home", "/boot"):
            d = sysinfo.storage(p)
            lines.append(f"{p}: " + (f"{sysinfo.human_bytes(d.value['free'])} free of {sysinfo.human_bytes(d.value['total'])}" if d.available else fmt(d)))
        disks.setText("\n".join(lines))
    lay.addWidget(label("<b>Updates</b>")); lay.addWidget(sy_updates)
    chk = QPushButton("Check for updates")
    def check_updates():
        chk.setEnabled(False); notice(sy_updates, "ok", "Checking (uses the network, can take a while)…")
        def done(res):
            chk.setEnabled(True)
            if isinstance(res, Exception):
                return notice(sy_updates, "error", str(res))
            if not res.available:
                notice(sy_updates, "warn", f"Could not check: {res.reason}"); ov_labels["updates"].setText(f"unavailable ({res.reason})"); return
            n = len(res.value)
            txt = "System is up to date." if n == 0 else f"{n} update(s) available. Run the upgrade in a terminal."
            notice(sy_updates, "ok", txt); ov_labels["updates"].setText(txt)
        background(updates_fn, done)
    chk.clicked.connect(check_updates); lay.addWidget(chk)
    ask = confirm or (lambda title, text: QMessageBox.question(win, title, text) == QMessageBox.Yes)
    details = QPlainTextEdit(); details.setReadOnly(True); details.setMaximumHeight(170); details.setAccessibleName("Details")
    def run_in_terminal(kind, title, text):
        if not ask(title, text):
            return notice(sy_status, "warn", "Cancelled. Nothing was changed.")
        ok, msg = launcher(maint_.terminal_command(kind))
        notice(sy_status, "ok" if ok else "error", msg + (" Follow the prompts in the terminal." if ok else ""))
    def start_update():
        pf = maint_.preflight()
        if pf["blockers"]:
            return notice(sy_status, "error", "Cannot start the update: " + " ".join(pf["blockers"]))
        run_in_terminal("update", "Full system update",
                        "This opens a terminal and runs 'sudo pacman -Syu' (refresh and upgrade everything together). You will see every "
                        "step and can answer its questions. Do not close the terminal until it finishes.\n\n" + "\n".join(pf["warnings"]))
    def clean_cache():
        run_in_terminal("clean-cache", "Clean package cache",
                        "This runs 'sudo paccache -r' in a terminal. It deletes OLD cached package files only, keeping the 3 most recent "
                        "versions of every package. Installed packages and your own files are not touched. Use 'Preview cache cleanup' first.")
    def show(title, fn, render):
        details.setPlainText(f"{title}…")
        def done(res):
            if isinstance(res, Exception):
                return details.setPlainText(f"{title}: failed ({res})")
            details.setPlainText(f"{title}:\n" + (render(res.value) if res.available else f"unavailable ({res.reason})"))
        background(fn, done)
    def restart_check():
        m = maint_.restart_needed()
        notice(sy_status, "ok" if m.available and not m.value else "warn",
               "Restart needed: the installed kernel differs from the running one (estimate)." if m.available and m.value
               else "No restart needed for the kernel (estimate; other libraries may still need a re-login)." if m.available
               else f"Cannot tell: {m.reason}")
    for text, fn in (
        ("Update system in a terminal…", start_update),
        ("Check if a restart is needed", restart_check),
        ("Show orphaned packages (list only)", lambda: show("Orphaned packages", maint_.orphans, lambda v: "\n".join(v) or "None.")),
        ("Show package cache size", lambda: show("Package cache", maint_.cache_size, lambda v: f"{sysinfo.human_bytes(v['bytes'])} in {v['files']} files")),
        ("Preview cache cleanup (nothing is deleted)", lambda: show("Cleanup preview", maint_.cleanup_preview, lambda v: "\n".join(v) or "Nothing to remove.")),
        ("Clean package cache in a terminal…", clean_cache),
        ("Show recent system errors", lambda: show("Recent errors (this boot)", maint_.recent_errors, lambda v: "\n".join(v) or "No errors logged this boot.")),
        ("Find large files in your home folder", lambda: show("Largest files in home", lambda: maint_.largest_files(home),
            lambda v: "\n".join(f"{sysinfo.human_bytes(sz)}  {pth}" for sz, pth in v["files"]) + ("\n(scan stopped early; list is partial)" if v["partial"] else "") or "No files.")),
    ):
        b = QPushButton(text); b.clicked.connect(lambda _=False, fn=fn: fn()); lay.addWidget(b)
    lay.addWidget(details)
    lay.addWidget(label(tools.UPDATE_GUIDANCE))
    lay.addWidget(label("<b>Recovery</b>")); lay.addWidget(label(tools.RECOVERY_GUIDANCE))
    lay.addWidget(label("The Control Centre never changes or deletes files itself. Updates and cache cleanup run in a terminal you can watch, only after you confirm. "
                        "Large-file results are for information; ChudOS offers no delete button on purpose."))
    lay.addWidget(sy_status); lay.addStretch(1)

    from PySide6.QtWidgets import QScrollArea
    for w in (ov, ap, prof_widget, so, dv, gm, sy):
        if w is prof_widget:
            pages.addWidget(w)
        else:
            sa = QScrollArea(); sa.setWidgetResizable(True); sa.setFrameShape(QScrollArea.NoFrame); sa.setWidget(w)
            pages.addWidget(sa)

    def on_nav(i):
        pages.setCurrentIndex(i)
        if SECTIONS[i] == "Overview":
            refresh_overview(); timer.start()
        else:
            timer.stop()
        if SECTIONS[i] == "System":
            refresh_disks()
    nav.currentRowChanged.connect(on_nav)
    for i in range(len(SECTIONS)):
        sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), win, activated=lambda i=i: nav.setCurrentRow(i))
        sc.setContext(Qt.WidgetWithChildrenShortcut)
    nav.setCurrentRow(0)   # fires on_nav(0) once via the signal
    win._nav, win._pages, win._timer, win._ov, win._so = nav, pages, timer, ov_labels, (so_enabled, so_vol, so_status, save_s)
    win._sy_updates, win._check_updates, win._dv = sy_updates, chk, (g_name, g_email, g_save, dv_status)
    win._sy = dict(status=sy_status, details=details, start_update=start_update, clean_cache=clean_cache, restart=restart_check)
    return win


def main() -> int:
    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print("chudos-control-center: PySide6 is not installed (package: pyside6).", file=sys.stderr)
        return 2
    app = QApplication(sys.argv[:1]); app.setApplicationName("chudos-control-center")
    w = build_window(); w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
