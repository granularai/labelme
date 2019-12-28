from __future__ import print_function

import distutils.spawn
import os.path
from setuptools import find_packages
from setuptools import setup
import shlex
import subprocess
import sys


PY3 = sys.version_info[0] == 3
PY2 = sys.version_info[0] == 2
assert PY3 or PY2


here = os.path.abspath(os.path.dirname(__file__))
version_file = os.path.join(here, 'labelus', '_version.py')
if PY3:
    import importlib
    version = importlib.machinery.SourceFileLoader(
        '_version', version_file
    ).load_module().__version__
else:
    assert PY2
    import imp
    version = imp.load_source('_version', version_file).__version__
del here


install_requires = [
    'matplotlib',
    'numpy',
    'Pillow>=2.8.0',
    'PyYAML',
    'qtpy',
    'termcolor',
]

# Find python binding for qt with priority:
# PyQt5 -> PySide2 -> PyQt4,
# and PyQt5 is automatically installed on Python3.
QT_BINDING = None

try:
    import PyQt5  # NOQA
    QT_BINDING = 'pyqt5'
except ImportError:
    pass

if QT_BINDING is None:
    try:
        import PySide2  # NOQA
        QT_BINDING = 'pyside2'
    except ImportError:
        pass

if QT_BINDING is None:
    try:
        import PyQt4  # NOQA
        QT_BINDING = 'pyqt4'
    except ImportError:
        if PY2:
            print(
                'Please install PyQt5, PySide2 or PyQt4 for Python2.\n'
                'Note that PyQt5 can be installed via pip for Python3.',
                file=sys.stderr,
            )
            sys.exit(1)
        assert PY3
        # PyQt5 can be installed via pip for Python3
        install_requires.append('PyQt5')
        QT_BINDING = 'pyqt5'
del QT_BINDING


if sys.argv[1] == 'release':
    if not distutils.spawn.find_executable('twine'):
        print(
            'Please install twine:\n\n\tpip install twine\n',
            file=sys.stderr,
        )
        sys.exit(1)

    commands = [
        'python tests/docs_tests/man_tests/test_labelus_1.py',
        'git tag v{:s}'.format(version),
        'git push origin master --tag',
        'python setup.py sdist',
        'twine upload dist/labelus-{:s}.tar.gz'.format(version),
    ]
    for cmd in commands:
        subprocess.check_call(shlex.split(cmd))
    sys.exit(0)


def get_long_description():
    with open('README.md') as f:
        long_description = f.read()
    try:
        import github2pypi
        return github2pypi.replace_url(
            slug='wkentaro/labelus', content=long_description
        )
    except Exception:
        return long_description


setup(
    name='labelus',
    version=version,
    packages=find_packages(),
    description='Image Pair Change Annotation with Python',
    long_description=get_long_description(),
    long_description_content_type='text/markdown',
    author='Sagar Verma',
    author_email='sagar@granular.ai',
    url='https://github.com/granularai/labelus',
    install_requires=install_requires,
    license='GPLv3',
    keywords='Image Annotation, Machine Learning, Change Annotation',
    classifiers=[
        'Development Status :: 5 - Production/Stable',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: Implementation :: CPython',
        'Programming Language :: Python :: Implementation :: PyPy',
    ],
    package_data={'labelus': ['icons/*', 'config/*.yaml']},
    entry_points={
        'console_scripts': [
            'labelus=labelus.main:main',
            'labelus_draw_json=labelus.cli.draw_json:main',
            'labelus_draw_label_png=labelus.cli.draw_label_png:main',
            'labelus_json_to_dataset=labelus.cli.json_to_dataset:main',
            'labelus_on_docker=labelus.cli.on_docker:main',
        ],
    },
    data_files=[('share/man/man1', ['docs/man/labelus.1'])],
)
