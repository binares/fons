import pathlib
from setuptools import setup, find_packages

HERE = pathlib.Path(__file__).parent
README = (HERE / "README.md").read_text()

setup(
   name='fons',
   version='0.1.0',
   description='A broad range of python tools. Some uses: round datetimes, '\
               'verify input data, execute functions by schedule, parse argv',
   long_description=README,
   long_description_content_type='text/markdown',
   url='https://github.com/binares/fons',
   author='binares',
   author_email='binares@protonmail.com',
   license='MIT',
   packages=find_packages(),
   exclude=['test'],
   python_requires='>=3.5',
   install_requires=[
       'aiohttp>=3.0',
       'requests>=2.0',
       'filelock>=3.0',
       'ntplib>=0.3.3',
       #these three are already required by pandas
       #'numpy>=1.19',
       #'python_dateutil>=2.1',
       #'pytz>=2011',
       'pandas>=0.21',
       'PyYAML>=3.10, <5',
   ],
)
