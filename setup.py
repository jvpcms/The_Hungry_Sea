import os
from setuptools import setup

_platform = os.environ.get('BUILD_PLATFORM')

setup(
    name='the-hungry-sea',
    options={
        'build_apps': {
            'console_apps': {
                'the-hungry-sea': 'pirate.py',
            },
            'include_patterns': [
                'assets/**/*',
            ],
            'platforms': [_platform] if _platform else [],
            'plugins': ['pandagl', 'p3openal_audio', 'p3ffmpeg'],
            'log_filename': '$USER_APPDATA/TheHungrySea/output.log',
            'log_append': False,
        }
    }
)
