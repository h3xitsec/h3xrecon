from setuptools import setup, find_packages

setup(
    name="h3xrecon",
    version="0.0.1",
    packages=find_packages(),  # Remove the 'where' parameter
    package_dir={},  # Remove this line as we're not remapping directories
    # install_requires=[
    #     "docopt",
    #     "loguru",
    #     "tabulate",
    #     "nats-py",
    #     # Add other dependencies your project needs
    # ],
)