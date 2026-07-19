import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

import utils  # noqa: E402
from utils import (  # noqa: E402
    detect_dotnet_desktop,
    detect_dotnet_sdk,
    detect_file_exists,
    detect_java,
    detect_windows_feature,
    dism_feature_state,
    is_component_installed,
    powershell_executable,
    run_hidden,
    sanitize_filename,
    wmi_feature_state,
)


class UtilsTests(unittest.TestCase):
    def test_filename_sanitization_blocks_path_components(self):
        self.assertEqual(sanitize_filename("../bad:name.exe"), "badname.exe")
        self.assertEqual(sanitize_filename("..."), "download.tmp")

    def test_file_detection(self):
        with tempfile.NamedTemporaryFile(dir=ROOT) as file:
            self.assertTrue(detect_file_exists(file.name))
        self.assertFalse(detect_file_exists(str(ROOT / "missing.file")))

    def test_file_detection_expands_environment_variables(self):
        with tempfile.NamedTemporaryFile(dir=ROOT) as file:
            name = Path(file.name).name
            with patch.dict(os.environ, {"RUNTIMEFIX_TEST_ROOT": str(ROOT)}):
                self.assertTrue(
                    detect_file_exists(f"%RUNTIMEFIX_TEST_ROOT%\\{name}")
                )
                self.assertFalse(
                    detect_file_exists("%RUNTIMEFIX_TEST_ROOT%\\missing.file")
                )

    def test_java_rejects_unknown_architecture(self):
        self.assertFalse(detect_java("arm64"))

    def test_detection_dispatches_config_values(self):
        cases = [
            ("dotnet", "8.0", "detect_dotnet_sdk", ("8.0",)),
            (
                "dotnet_desktop",
                "8.0:x86:aspnet",
                "detect_dotnet_desktop",
                ("8.0", "x86", "aspnet"),
            ),
            ("vcredist", "2015:x64", "detect_vcredist", ("2015", "x64")),
            ("registry", "HKLM\\Example", "detect_registry_key", ("HKLM\\Example",)),
            ("java", "x86", "detect_java", ("x86",)),
            ("file", "C:\\example.dll", "detect_file_exists", ("C:\\example.dll",)),
            ("dotnet_framework", "533320", "detect_dotnet_framework", (533320,)),
            ("jdk", "21", "detect_jdk_version", ("21",)),
            (
                # Tarama yolu ÖNBELLEKTEN okur — alt süreç açan sorgu değil
                "windows_feature",
                "DirectPlay",
                "detect_windows_feature_cached",
                ("DirectPlay",),
            ),
        ]
        for detect_type, value, target, expected_args in cases:
            with (
                self.subTest(detect_type=detect_type),
                patch(f"utils.{target}", return_value=True) as detector,
            ):
                self.assertTrue(
                    is_component_installed(
                        {
                            "detect_type": detect_type,
                            "detect_value": value,
                        }
                    )
                )
                detector.assert_called_once_with(*expected_args)

    def test_dism_feature_state_is_parsed_from_real_output_format(self):
        completed = SimpleNamespace(
            returncode=0,
            stdout=(
                "Feature Name : DirectPlay\r\n"
                "Display Name : DirectPlay\r\n"
                "State : Enable Pending\r\n"
            ),
            stderr="",
        )
        with patch("utils.run_hidden", return_value=completed) as run:
            self.assertEqual(dism_feature_state("DirectPlay"), "enable pending")
        command = run.call_args.args[0]
        self.assertIn("/get-featureinfo", command)
        self.assertIn("/English", command)  # çıktı dili sabitlenmeli

    def test_wmi_install_states_are_mapped(self):
        # Win32_OptionalFeature.InstallState: 1=etkin, 2=devre dışı, 3=yok
        for value, expected in (("1", "enabled"), ("2", "disabled"), ("3", "absent")):
            completed = SimpleNamespace(
                returncode=0, stdout=f"STATE={value}\r\n", stderr=""
            )
            with self.subTest(value=value), patch(
                "utils.run_hidden", return_value=completed
            ):
                self.assertEqual(wmi_feature_state("DirectPlay"), expected)

    def test_feature_detection_maps_states_to_installed(self):
        cases = {"1": True, "2": False, "3": False}
        for value, expected in cases.items():
            completed = SimpleNamespace(
                returncode=0, stdout=f"STATE={value}\r\n", stderr=""
            )
            with self.subTest(value=value), patch(
                "utils.run_hidden", return_value=completed
            ):
                self.assertIs(detect_windows_feature("DirectPlay"), expected)

    def test_dism_is_used_when_wmi_cannot_answer(self):
        """WMI yanıt vermezse DISM'e düşülmeli (yükseltilmiş ortam)."""
        with (
            patch("utils.wmi_feature_state", return_value=""),
            patch("utils.dism_feature_state", return_value="enable pending") as dism,
        ):
            self.assertTrue(detect_windows_feature("DirectPlay"))
        dism.assert_called_once_with("DirectPlay")

    def test_unreadable_state_is_never_assumed_installed(self):
        """Sorgulanamayan özellik 'kurulu' sayılmamalı."""
        with (
            patch("utils.wmi_feature_state", return_value=""),
            patch("utils.dism_feature_state", return_value=""),
        ):
            self.assertFalse(detect_windows_feature("DirectPlay"))

    def test_malformed_feature_name_is_rejected_before_querying(self):
        """Özellik adı WQL sorgusuna girer; tırnak içeren ad hiç çalıştırılmamalı."""
        with patch("utils.run_hidden") as run:
            self.assertEqual(wmi_feature_state("DirectPlay' OR '1'='1"), "")
        run.assert_not_called()

    @unittest.skipUnless(os.name == "nt", "Windows özellikleri yalnızca Windows'ta")
    def test_real_feature_states_match_the_system(self):
        """
        Taklit değil: gerçek Windows'a sorulur ve bağımsız bir kaynakla
        karşılaştırılır. NetFx3'ün durumu registry tespitiyle aynı çıkmalı.
        """
        from utils import detect_dotnet_framework35

        netfx_state = wmi_feature_state("NetFx3")
        if not netfx_state:
            self.skipTest("WMI özellik sorgusu bu ortamda yanıt vermiyor")
        self.assertEqual(
            detect_windows_feature("NetFx3"), detect_dotnet_framework35()
        )
        # Var olmayan özellik "kurulu" görünmemeli
        self.assertFalse(detect_windows_feature("BoyleBirOzellikYok"))

    @unittest.skipUnless(os.name == "nt", "PowerShell yalnızca Windows'ta")
    def test_powershell_helper_is_actually_runnable(self):
        """
        Hem özellik tespiti hem imza doğrulaması PowerShell'e dayanıyor.
        Bu test olmadan, PowerShell bulunamadığında ilgili canlı testler
        sessizce "atlandı" görünür ve gerçek arıza fark edilmez.
        """
        executable = powershell_executable()
        self.assertTrue(os.path.isfile(executable), f"bulunamadı: {executable}")
        result = run_hidden(
            [executable, "-NoProfile", "-NonInteractive", "-Command", "Write-Output OK"],
            timeout=60,
        )
        self.assertEqual((result.stdout or "").strip(), "OK")

    def test_dotnet_versions_are_read_as_registry_values_not_subkeys(self):
        """
        .NET sürümleri anahtar altında DEĞER adı olarak durur ("8.0.25" = 1).
        Alt anahtar sayan eski kod hep boş dönüyor, tespit CLI'ya düşüyor ve
        her taramada ~24 alt süreç açılıyordu; kurulu sürüm bu yüzden donuyordu.
        """
        versions = ["8.0.25", "10.0.10", "6.0.36"]

        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

        def fake_query_info(_key):
            return (0, len(versions), 0)  # alt anahtar YOK, değer VAR

        def fake_enum_value(_key, index):
            return (versions[index], 1, 4)

        with (
            patch("utils.winreg.OpenKey", return_value=FakeKey()),
            patch("utils.winreg.QueryInfoKey", side_effect=fake_query_info),
            patch("utils.winreg.EnumValue", side_effect=fake_enum_value),
        ):
            found = utils._dotnet_versions_in_registry(r"SOFTWARE\ornek")
        self.assertEqual(sorted(set(found)), sorted(set(versions)))

    def test_dotnet_detection_needs_no_subprocess_when_disk_has_it(self):
        """Disk kaynağı varken alt süreç açılmamalı — kilitlenmenin yolu budur."""
        with (
            patch("utils._dotnet_versions_on_disk", return_value=["8.0.15", "9.0.4"]),
            patch("utils.run_hidden") as run,
        ):
            self.assertTrue(detect_dotnet_desktop("8.0", "x64", "desktop"))
            self.assertTrue(detect_dotnet_sdk("9.0"))
            run.assert_not_called()

    def test_registry_is_used_when_disk_is_unavailable(self):
        with (
            patch("utils._dotnet_versions_on_disk", return_value=[]),
            patch("utils._dotnet_versions_in_registry", return_value=["10.0.10"]),
            patch("utils.run_hidden", side_effect=AssertionError("alt süreç açıldı")),
        ):
            self.assertTrue(detect_dotnet_desktop("10.0", "x64", "desktop"))

    def test_subprocess_never_inherits_an_invalid_stdin(self):
        """
        Konsolsuz (pencere modunda paketlenmiş) uygulamada devralınan stdin
        geçersizdir; alt süreç okumaya kalkarsa süresiz bloke olur.
        """
        with patch("utils.subprocess.run") as run:
            run_hidden(["whoami"])
        self.assertEqual(
            run.call_args.kwargs.get("stdin"), subprocess.DEVNULL
        )

    def test_full_config_scan_never_spawns_a_subprocess(self):
        """
        Kurulu sürümdeki donmanın ortak paydası buydu: tarama sırasında alt
        süreç açmak. Gerçek config'in tamamı taranırken tek bir alt süreç bile
        açılmamalı; Windows özelliği sorgusu arka plana taşındı.
        """
        config = json.loads(
            (ROOT / "data" / "config.json").read_text(encoding="utf-8")
        )
        with patch("utils.run_hidden") as run:
            for component in config["components"]:
                is_component_installed(component)
        run.assert_not_called()

    def test_feature_cache_round_trip(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                self.assertFalse(utils.detect_windows_feature_cached("DirectPlay"))
                utils.write_feature_cache({"DirectPlay": True})
                self.assertTrue(utils.detect_windows_feature_cached("DirectPlay"))
                self.assertFalse(utils.detect_windows_feature_cached("Bilinmeyen"))

    def test_unreadable_cache_reports_not_installed(self):
        """Bozuk önbellek 'kurulu' sayılmamalı."""
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                path = Path(utils._feature_cache_path())
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("{bozuk", encoding="utf-8")
                self.assertEqual(utils.read_feature_cache(), {})
                self.assertFalse(utils.detect_windows_feature_cached("DirectPlay"))

    def test_fresh_cache_prevents_repeated_background_queries(self):
        """
        Taze kayıt varken arka plan sorgusu da çalışmamalı: her açılışta alt
        süreç açmak, donmanın kaynağıydı.
        """
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                features = ["DirectPlay"]
                self.assertTrue(utils.feature_cache_is_stale(features))  # ilk açılış

                utils.write_feature_cache({"DirectPlay": True})
                self.assertFalse(utils.feature_cache_is_stale(features))

                # Bilinmeyen bir özellik eklenirse yeniden sorgulanmalı
                self.assertTrue(utils.feature_cache_is_stale(["DirectPlay", "NetFx3"]))

                # Kayıt eskiyince yeniden sorgulanmalı
                stale = utils.read_feature_cache()
                stale["_checked_at"] = time.time() - utils.FEATURE_CACHE_TTL_SECONDS - 1
                Path(utils._feature_cache_path()).write_text(
                    json.dumps(stale), encoding="utf-8"
                )
                self.assertTrue(utils.feature_cache_is_stale(features))

    def test_successful_install_records_feature_state(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            with patch.dict(os.environ, {"LOCALAPPDATA": directory}):
                utils.remember_feature_state("DirectPlay", True)
                self.assertTrue(utils.detect_windows_feature_cached("DirectPlay"))

    def test_unknown_detection_type_is_not_assumed_installed(self):
        self.assertFalse(
            is_component_installed(
                {"detect_type": "unknown", "detect_value": ""}
            )
        )


if __name__ == "__main__":
    unittest.main()
