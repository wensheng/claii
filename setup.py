import os
import setuptools

VERSION = '0.1.0'


with open('README.md', encoding='utf8') as f:
    long_description = f.read()

setuptools.setup(
    name='claii',
    version=VERSION,
    author='Wensheng Wang',
    author_email='wenshengwang@gmail.com',
    description='claii - Command Line AI Interface',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/wensheng/claii',
    project_urls={
        'Issues': 'https://github.com/wensheng/claii/issues',
    },
    license='Apache License, Version 2.0',
    packages=['claii'],
    entry_points={
        'console_scripts': [
            'claii = claii:cli'
        ]
    },
    install_requires=[
        'click',
        'openai',
        'chromadb',
        'python-dotenv',
    ],
    python_requires='>=3.6',
    include_package_data=True,
)
