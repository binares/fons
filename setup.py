from setuptools import setup, find_packages

setup(
   name='fons',
   version='0.1.0',
   description='A broad range of python tools. Some uses: round datetimes, verify input data, execute functions by schedule, parse argv',
   author='binares',
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
