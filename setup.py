from setuptools import setup, find_packages

setup(
    name='selfcord',
    version='1.0.0',
    description='An optimized version of discord.py 1.7.3 supporting API v9',
    author='Nothing',
    author_email='support@cuddly-team.kro.kr',
    url='https://github.com/Nothing-64/selfcord',
    packages=find_packages(),
    install_requires=[
        'aiohttp', 
        'websockets'
    ],
    classifiers=[
        'Programming Language :: Python :: 3',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
    python_requires='>=3.6',
)
