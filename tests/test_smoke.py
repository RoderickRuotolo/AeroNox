import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aeronox.catalog import PaletteCatalog
from aeronox.contrast import contrast_ratio
from aeronox.models import Palette, PaletteError
from aeronox.paths import XDGPaths


class FoundationSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='aeronox home ')
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.env = dict(os.environ, HTOPRC="", HOME=str(self.home),
                        XDG_CONFIG_HOME=str(self.home/'config'),
                        XDG_STATE_HOME=str(self.home/'state'),
                        XDG_DATA_HOME=str(self.home/'data'),
                        PYTHONDONTWRITEBYTECODE='1')

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "aeronox", *args], env=self.env, cwd=self.home,
                              capture_output=True, text=True, check=False)

    def test_cli_queries_and_no_mutation(self):
        sentinel = self.home/'.vimrc'
        sentinel.write_bytes(b'personal settings\n')
        for args in [('--help',), ('--version',), ('doctor',), ('palette','list'),
                     ('palette','contrast'), ('palette','show','aviation-red'),
                     ('palette','show','nvis-green-a')]:
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(sentinel.read_bytes(), b'personal settings\n')
        self.assertEqual(list(self.home.iterdir()), [sentinel])
        data = json.loads(self.run_cli('palette','show','aviation-red').stdout)
        self.assertEqual(data['colors']['foreground'], '#CC3333')

    def test_errors(self):
        for args, status in [(('install', '--components', 'unknown'), 2),
                             (('apply', 'unknown'), 2),
                             (('palette','show','../secret'),1), ((),2)]:
            with self.subTest(args=args):
                self.assertEqual(self.run_cli(*args).returncode, status)
        self.assertEqual(list(self.home.iterdir()), [])

    def test_packaged_palette_validation(self):
        for palette in PaletteCatalog().list():
            self.assertEqual(len(palette.ansi16),16)
            self.assertEqual(Palette.from_dict(palette.to_dict()),palette)
            with self.assertRaises(TypeError):
                palette.colors['background'] = '#FFFFFF'
        original = PaletteCatalog().get('aviation-red').to_dict()
        for field,value in [('schema_version',True),('schema_version',2),('id','../secret'),
                            ('colors',{}),('ansi16',['#000000']*15),
                            ('ansi16',['#GGGGGG']*16),('name',' '),('description',None)]:
            with self.subTest(field=field,value=value):
                data = copy.deepcopy(original)
                data[field] = value
                with self.assertRaises(PaletteError):
                    Palette.from_dict(data)
        for color in ['#FFF','red',None,12,'#000000\n']:
            data = copy.deepcopy(original)
            data['colors']['foreground'] = color
            with self.assertRaises(PaletteError):
                Palette.from_dict(data)

    def test_xdg_resolution(self):
        default = XDGPaths.resolve({'HOME':str(self.home)})
        self.assertEqual(default.config,self.home/'.config/aeronox')
        self.assertEqual(default.state,self.home/'.local/state/aeronox')
        self.assertEqual(default.data,self.home/'.local/share/aeronox')
        self.assertEqual(XDGPaths.resolve(dict(HOME=str(self.home), XDG_CONFIG_HOME='relative',
                                             XDG_STATE_HOME='', XDG_DATA_HOME='../bad')),default)
        self.assertEqual(XDGPaths.resolve(self.env).config,self.home/'config/aeronox')
        self.assertEqual(list(self.home.iterdir()),[])

    def test_contrast(self):
        self.assertAlmostEqual(contrast_ratio('#000000','#FFFFFF'),21)
        self.assertAlmostEqual(contrast_ratio('#123456','#123456'),1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
