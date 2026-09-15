"""Configuration migration and atomic override persistence."""
import configparser
from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'bCNC'))
import Utils


class ConfigurationTest(unittest.TestCase):
    def test_save_preserves_runtime_defaults_and_roundtrips_user_data(self):
        with tempfile.TemporaryDirectory() as folder:
            user = str(Path(folder) / 'user.ini')
            config = configparser.ConfigParser()
            config.read(Utils.iniSystem)
            config.set('CNC', 'header', 'G90\nM5')
            config.set('Plotter', 'pressure', '350')
            config.set('Plotter', 'profile_library', '{"tools": []}')
            config.set('Connection', 'port', 'socket://plotter.local:8888')
            config.add_section('Box'); config.set('Box', 'n', '5')
            before = deepcopy(config)
            with patch.object(Utils, 'config', config), patch.object(Utils, 'iniUser', user), patch.object(Utils, 'delIcons'):
                Utils.saveConfiguration()
                self.assertEqual(dict(config['CNC']), dict(before['CNC']))
                Utils.saveConfiguration()
            saved = configparser.ConfigParser(); saved.read(user)
            self.assertFalse(saved.has_section('Box'))
            self.assertFalse(saved.has_option('CNC', 'accuracy'))
            merged = configparser.ConfigParser(); merged.read([Utils.iniSystem, user])
            for section, key in [('CNC','header'), ('Plotter','pressure'), ('Plotter','profile_library'), ('Connection','port')]:
                self.assertEqual(merged.get(section,key), before.get(section,key))
            self.assertEqual(merged.get('CNC','accuracy'), before.get('CNC','accuracy'))

    def test_legacy_overcut_is_migrated(self):
        config = configparser.ConfigParser()
        config.read_dict({'DragKnife': {'overcut': '2'}})
        with patch.object(Utils, 'config', config):
            saved = Utils.cleanConfiguration()
        self.assertEqual(saved.get('Plotter', 'overcut'), '2')
        self.assertFalse(saved.has_section('DragKnife'))

    def test_failed_replace_keeps_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'user.ini'; path.write_text('previous')
            with patch.object(Utils, 'iniUser', str(path)), patch('os.replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError): Utils.saveConfiguration()
            self.assertEqual(path.read_text(), 'previous')
            self.assertFalse(list(Path(folder).glob('.foil-config-*')))
            self.assertEqual(Path(str(path) + '.before-cleanup').read_text(), 'previous')

    def test_schema_keeps_dynamic_consumers_and_removes_unknown_settings(self):
        config = configparser.ConfigParser(interpolation=None)
        config.read(Utils.iniSystem)
        config.read_dict({'ObsoletePlugin': {'enabled': '1'},
                          'Connection': {'pendant': '1', 'openserial': '1'},
                          'File': {'recent.0': '/tmp/project.foil'},
                          'TextInsertion': {'height': '20', 'font': '/tmp/font.ttf'},
                          'Controller': {'grbl_140': '2'},
                          'Error': {'G4': '1'},
                          'CNC': {'header': '(100% custom)\nM5'}})
        with patch.object(Utils, 'config', config):
            saved = Utils.cleanConfiguration()
        self.assertFalse(saved.has_section('ObsoletePlugin'))
        self.assertFalse(saved.has_option('Connection', 'pendant'))
        for section, key in [('Connection','openserial'), ('File','recent.0'),
                             ('TextInsertion','font'), ('Controller','grbl_140'),
                             ('Error','g4'), ('CNC','header')]:
            self.assertEqual(saved.get(section,key), config.get(section,key))

    def test_reload_does_not_carry_settings_from_previous_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'new-user.ini'
            stale = configparser.ConfigParser(interpolation=None)
            stale.read_dict({'Plotter': {'pressure': '999'}, 'OldPlugin': {'n': '5'}})
            with patch.object(Utils, 'config', stale), patch.object(Utils, 'iniUser', str(path)):
                Utils.loadConfiguration()
                self.assertFalse(Utils.config.has_section('OldPlugin'))
                self.assertFalse(Utils.config.has_option('Plotter', 'pressure'))
                self.assertTrue(Utils.config.has_section('Error'))
