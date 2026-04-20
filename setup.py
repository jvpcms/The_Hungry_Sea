from setuptools import setup

setup(
    name='the-hungry-sea',
    options={
        'build_apps': {
            'gui_apps': {
                'the-hungry-sea': 'pirate.py',
            },
            'include_patterns': [
                'assets/**/*',
            ],
            'plugins': ['pandagl', 'p3openal_audio'],
            'log_filename': '$USER_APPDATA/TheHungrySea/output.log',
            'log_append': False,
        }
    }
)
