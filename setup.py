from setuptools import setup, find_packages
import os

# Get the absolute path to the README.md file
readme_path = os.path.join(os.path.dirname(__file__), 'README.md')

setup(
    name="h3xrecon",
    version="0.0.3",
    packages=find_packages(where='src'),  # Specify the source directory
    package_dir={'': 'src'},  # Indicate that packages are in the 'src' directory
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
    long_description="h3xrecon bug bounty reconnaissance automation",
    long_description_content_type="text/markdown",
    url="https://github.com/h3xitsec/h3xrecon",  # Your repository URL
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",  # Adjust license as needed
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.9",  # Adjust minimum Python version as needed

    extras_require={
        'test': [
            'pytest>=7.0.0',
            'pytest-asyncio>=0.21.0',
        ]
    },
)
