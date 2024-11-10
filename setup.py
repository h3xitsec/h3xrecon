from setuptools import setup, find_packages
import os

# Get the absolute path to the README.md file
readme_path = os.path.join(os.path.dirname(__file__), 'README.md')

# Read the README.md content
with open(readme_path, 'r', encoding='utf-8') as f:
    long_description = f.read()

setup(
    name="h3xrecon",
    version="0.0.3",
    packages=find_packages(where='src'),  # Corrected package discovery
    package_dir={'': 'src'},  # Corrected package directory
    install_requires=[
        "docopt",
        "loguru",
        "tabulate",
        "nats-py",
        "asyncpg",
        "python-dotenv",
        "redis",
        "jsondiff"
    ],
    entry_points={
        'console_scripts': [
            'h3xrecon=h3xrecon.cli.main:main',
        ],
    },
    author="h3xit",
    description="h3xrecon bug bounty reconnaissance automation",
    long_description=long_description,  # Use the actual README content
    long_description_content_type="text/markdown",
    url="https://github.com/h3xitsec/h3xrecon",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",

    extras_require={
        'test': [
            'pytest>=7.0.0',
            'pytest-asyncio>=0.21.0',
        ]
    },
)
