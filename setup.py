from setuptools import setup

setup(
    name='dead-reckoning',
    options={
        'build_apps': {
            'gui_apps': {
                'dead-reckoning': 'pirate.py',
            },
            'include_patterns': [
                'assets/**/*',
            ],
            'plugins': ['pandagl', 'p3openal_audio'],
            'log_filename': '$USER_APPDATA/DeadReckoning/output.log',
            'log_append': False,
        }
    }
)
