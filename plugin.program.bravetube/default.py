import os
import shlex
import shutil
import subprocess
import sys

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo("id")
ADDON_NAME = ADDON.getAddonInfo("name")

TV_USER_AGENT = (
    "Mozilla/5.0 (SMART-TV; Linux; Tizen 5.0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) 69.0.3497.106.1 TV Safari/537.36"
)
URL_TV = "https://www.youtube.com/tv"
URL_DESKTOP = "https://www.youtube.com"


def log(msg, level=xbmc.LOGINFO):
    xbmc.log("[%s] %s" % (ADDON_ID, msg), level)


def flatpak_has_brave():
    if not shutil.which("flatpak"):
        return False
    try:
        r = subprocess.run(
            ["flatpak", "info", "com.brave.Browser"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return r.returncode == 0
    except Exception:
        return False


def find_brave():
    """Return (command_prefix_list, is_flatpak) or (None, False)."""
    custom = ADDON.getSetting("brave_path").strip()
    if custom:
        return [custom], False

    if sys.platform.startswith("win"):
        roots = [os.environ.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        for root in filter(None, roots):
            p = os.path.join(root, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
            if os.path.exists(p):
                return [p], False
    elif sys.platform == "darwin":
        p = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        if os.path.exists(p):
            return [p], False
    else:
        for name in ("brave-browser", "brave", "brave-browser-stable"):
            found = shutil.which(name)
            if found:
                return [found], False
        if flatpak_has_brave():
            return ["flatpak", "run", "com.brave.Browser"], True
    return None, False


def build_command(prefix, is_flatpak):
    tv_mode = ADDON.getSettingInt("mode") == 0
    cmd = list(prefix)

    cmd += [
        "--kiosk",
        "--start-fullscreen",
        "--no-first-run",
        "--no-default-browser-check",
        "--autoplay-policy=no-user-gesture-required",
        "--password-store=basic",
        "--disable-features=Translate",
    ]

    if not is_flatpak:
        profile = os.path.join(
            xbmcvfs.translatePath(ADDON.getAddonInfo("profile")), "brave-profile"
        )
        os.makedirs(profile, exist_ok=True)
        cmd.append("--user-data-dir=%s" % profile)

    if tv_mode:
        cmd.append("--user-agent=%s" % TV_USER_AGENT)

    if ADDON.getSettingBool("hwaccel") and sys.platform.startswith("linux"):
        cmd.append(
            "--enable-features=VaapiVideoDecoder,VaapiVideoEncoder,VaapiIgnoreDriverChecks"
        )
        cmd.append("--ignore-gpu-blocklist")

    extra = ADDON.getSetting("extra_args").strip()
    if extra:
        cmd += shlex.split(extra, posix=not sys.platform.startswith("win"))

    cmd.append(URL_TV if tv_mode else URL_DESKTOP)
    return cmd


def run():
    prefix, is_flatpak = find_brave()
    if not prefix:
        xbmcgui.Dialog().ok(
            ADDON_NAME,
            "Brave wasn't found. Install it, or set the path to the Brave "
            "executable in the add-on settings.",
        )
        return

    cmd = build_command(prefix, is_flatpak)
    log("Launching: %s" % " ".join(cmd))

    player = xbmc.Player()
    if player.isPlaying():
        player.stop()

    monitor = xbmc.Monitor()
    xbmc.audioSuspend()
    try:
        kwargs = {}
        if sys.platform.startswith("win"):
            kwargs["creationflags"] = 0x00000008  # DETACHED_PROCESS
        proc = subprocess.Popen(cmd, **kwargs)

        while proc.poll() is None:
            if monitor.waitForAbort(1):
                log("Kodi is shutting down, terminating Brave")
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                break
        log("Brave exited with code %s" % proc.returncode)
    except Exception as exc:
        log("Launch failed: %s" % exc, xbmc.LOGERROR)
        xbmcgui.Dialog().notification(ADDON_NAME, "Couldn't start Brave", xbmcgui.NOTIFICATION_ERROR)
    finally:
        xbmc.audioResume()


if __name__ == "__main__":
    run()
