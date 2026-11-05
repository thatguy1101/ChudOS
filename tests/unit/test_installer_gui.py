import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from chudos_installer import form as formmod
from chudos_installer.disks import Disk

GIB = 1024**3


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def disks():
    return [Disk("/dev/sda", 100 * GIB, model="VM"), Disk("/dev/sdb", 8 * GIB, usable=False, reason="too small")]


def make(qapp, sent):
    from chudos_installer.gui import build_window
    return build_window(disks_fn=disks, tz_fn=lambda: ["Australia/Perth", "UTC"], start_backend=lambda req, feed: sent.append((req, feed)))


# ---- form logic (no Qt) ----
def good_form(**o):
    f = formmod.Form(disk="/dev/sda", fullname="Max", hostname="box", username="max", password="pw", password2="pw", timezone="UTC",
                     usable_disks={"/dev/sda"}, confirm="/dev/sda")
    for k, v in o.items(): setattr(f, k, v)
    return f


def test_form_confirm_gate():
    assert good_form().confirm_ok()
    for bad in (dict(confirm=""), dict(confirm="/dev/sdb"), dict(confirm="sda"), dict(confirm="/dev/sda "), dict(disk="/dev/sdb", confirm="/dev/sdb"),
                dict(password2="x"), dict(username="root"), dict(hostname="-x"), dict(timezone=""), dict(fullname="a:b")):
        assert not good_form(**bad).confirm_ok(), bad
    with pytest.raises(ValueError):
        good_form(confirm="").request()


def test_request_shape_has_confirmation_and_password():
    r = good_form().request()
    assert r["confirm_erase"] == "/dev/sda" and r["settings"]["password"] == "pw" and r["settings"]["disk"] == "/dev/sda"


# ---- window ----
def type_text(w, text):
    w.setText(text)


def fill_user(c):
    c["f_name"].setText("Max Q"); c["f_host"].setText("chudbox"); c["f_user"].setText("max"); c["f_pw"].setText("pw1"); c["f_pw2"].setText("pw1")


def test_flow_requires_disk_user_and_typed_confirmation(qapp):
    from PySide6.QtCore import Qt
    sent = []; w = make(qapp, sent); c = w._ctl
    assert c["stack"].currentIndex() == 0 and c["nxt"].isEnabled()
    c["go_next"]()                                           # -> disk page
    assert c["stack"].currentIndex() == 1 and not c["nxt"].isEnabled()          # nothing preselected
    assert c["lst"].count() == 2 and not (c["lst"].item(1).flags() & Qt.ItemIsSelectable) and not (c["lst"].item(1).flags() & Qt.ItemIsEnabled)
    c["lst"].setCurrentRow(0); assert c["nxt"].isEnabled()
    c["go_next"](); assert c["stack"].currentIndex() == 2 and not c["nxt"].isEnabled()
    fill_user(c); assert c["nxt"].isEnabled()
    c["go_next"](); c["go_next"]()
    assert c["stack"].currentIndex() == 4 and not c["nxt"].isEnabled() and c["nxt"].text() == "Erase and install"
    c["f_conf"].setText("/dev/sd"); assert not c["nxt"].isEnabled()
    c["go_next"]()
    assert not sent and c["stack"].currentIndex() == 4       # cannot start without exact confirmation
    c["f_conf"].setText("/dev/sda"); assert c["nxt"].isEnabled()
    c["go_next"]()
    assert len(sent) == 1 and c["stack"].currentIndex() == 5
    req = json.loads(sent[0][0]); assert req["confirm_erase"] == "/dev/sda" and req["settings"]["username"] == "max" and req["settings"]["password"] == "pw1"


def test_password_mismatch_blocks(qapp):
    w = make(qapp, []); c = w._ctl; c["go_next"](); c["lst"].setCurrentRow(0); c["go_next"]()
    fill_user(c); c["f_pw2"].setText("different"); assert not c["nxt"].isEnabled()


def test_cannot_close_or_go_back_while_installing(qapp):
    from PySide6.QtGui import QCloseEvent
    sent = []; w = make(qapp, sent); c = w._ctl
    c["go_next"](); c["lst"].setCurrentRow(0); c["go_next"](); fill_user(c); c["go_next"](); c["go_next"](); c["f_conf"].setText("/dev/sda"); c["go_next"]()
    ev = QCloseEvent(); w.closeEvent(ev); assert not ev.isAccepted()
    assert not c["back"].isEnabled()


def run_to_install(qapp):
    sent = []; w = make(qapp, sent); c = w._ctl
    c["go_next"](); c["lst"].setCurrentRow(0); c["go_next"](); fill_user(c); c["go_next"](); c["go_next"](); c["f_conf"].setText("/dev/sda"); c["go_next"]()
    return w, c, sent[0][1]


def test_progress_error_and_done_events(qapp):
    w, c, feed = run_to_install(qapp)
    feed(json.dumps({"type": "step", "i": 3, "n": 10, "title": "Partition"}) + "\n" + json.dumps({"type": "log", "line": "hello"}) + "\nplain text line\n")
    assert c["bar"].value() == 3 and "hello" in c["log"].toPlainText() and "plain text line" in c["log"].toPlainText()
    feed(json.dumps({"type": "error", "step": "pacstrap", "message": "boom", "disk_modified": True}) + "\n")
    assert c["stack"].currentIndex() == 6 and "boom" in c["res"].text() and "partly modified" in c["res"].text() and c["nxt"].text() == "Close"
    from PySide6.QtGui import QCloseEvent
    ev = QCloseEvent(); w.closeEvent(ev); assert ev.isAccepted()


def test_done_event_offers_restart(qapp):
    w, c, feed = run_to_install(qapp)
    feed(json.dumps({"type": "done"}) + "\n")
    assert c["stack"].currentIndex() == 6 and c["nxt"].text() == "Restart now" and "installed" in c["res"].text()


def test_error_before_changes_says_disk_untouched(qapp):
    w, c, feed = run_to_install(qapp)
    feed(json.dumps({"type": "error", "step": "preflight", "message": "No internet connection.", "disk_modified": False}) + "\n")
    assert "NOT changed" in c["res"].text()


def test_terminal_hint_present(qapp):
    from PySide6.QtWidgets import QLabel
    w = make(qapp, [])
    assert any("Ctrl+Alt+F3" in l.text() for l in w.findChildren(QLabel))
