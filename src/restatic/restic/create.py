import os
import tempfile

from ..utils import get_current_wifi
from ..models import SourceDirModel, WifiSettingModel
from .restic_thread import ResticThread


class ResticCreateThread(ResticThread):
    def process_result(self, result):
        if result["returncode"] in [0, 1]:

            """
            FIXME: can be fixed, when https://github.com/restic/restic/issues/2096 is implemented
            new_snapshot, created = ArchiveModel.get_or_create(
                snapshot_id=result['data']['archive']['id'],
                defaults={
                    'name': result['data']['archive']['name'],
                    'time': parser.parse(result['data']['archive']['start']),
                    'repo': result['params']['repo_id'],
                    'duration': result['data']['archive']['duration'],
                    'size': result['data']['archive']['stats']['deduplicated_size']
                }
            )
            """

    def log_event(self, msg):
        self.app.backup_log_event.emit(msg)

    def started_event(self):
        self.app.backup_started_event.emit()
        self.app.backup_log_event.emit("Backup started.")

    def finished_event(self, result):
        self.app.backup_finished_event.emit(result)
        self.app.backup_log_event.emit("Backup finished.")

    @classmethod
    def prepare(cls, profile):
        """
        `restic init` is called from different places and needs some preparation.
        Centralize it here and return the required arguments to the caller.
        """
        ret = super().prepare(profile)
        if not ret["ok"]:
            return ret
        else:
            ret["ok"] = False  # Set back to false, so we can do our own checks here.

        n_backup_folders = SourceDirModel.select().count()
        if n_backup_folders == 0:
            ret["message"] = "Add some folders to back up first."
            return ret

        current_wifi = get_current_wifi()
        if current_wifi is not None:
            wifi_is_disallowed = WifiSettingModel.select().where(
                (WifiSettingModel.ssid == current_wifi)
                & (WifiSettingModel.allowed is False)
                & (WifiSettingModel.profile == profile.id)
            )
            if wifi_is_disallowed.count() > 0 and profile.repo.is_remote_repo():
                ret["message"] = "Current Wifi is not allowed."
                return ret

        if not profile.repo.is_remote_repo() and not os.path.exists(profile.repo.url):
            ret["message"] = "Repo folder not mounted or moved."
            return ret

        cmd = ["restic", "backup", "-r", profile.repo.url, "--json"]

        # Add excludes
        # Partly inspired by resticmatic/resticmatic/restic/create.py
        if profile.exclude_patterns is not None:
            exclude_dirs = []
            for p in profile.exclude_patterns.split("\n"):
                if p.strip():
                    expanded_directory = os.path.expanduser(p.strip())
                    exclude_dirs.append(expanded_directory)

            if exclude_dirs:
                pattern_file = tempfile.NamedTemporaryFile("w", delete=False)
                pattern_file.write("\n".join(exclude_dirs))
                pattern_file.flush()
                cmd.extend(["--exclude-from", pattern_file.name])

        if profile.exclude_if_present is not None:
            for f in profile.exclude_if_present.split("\n"):
                if f.strip():
                    cmd.extend(["--exclude-if-present", f.strip()])

        for f in SourceDirModel.select().where(SourceDirModel.profile == profile.id):
            cmd.append(f.dir)

        ret["message"] = "Starting backup.."
        ret["ok"] = True
        ret["cmd"] = cmd

        return ret
