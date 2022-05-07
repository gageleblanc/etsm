import setuptools
import etsm

# with open("readme.md", "r") as fh:
#     long_description = fh.read()

setuptools.setup(
    name='et-server-manager',
    version=etsm.__version__,
    scripts=[],
    entry_points={
        'console_scripts': ["etsm = etsm.cli.__main__:cli"]
    },
    author="Gage LeBlanc",
    author_email="gleblanc@symnet.io",
    description="Enemy Territory server manager",
    # long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/gageleblanc/etsm",
    packages=setuptools.find_packages(),
    install_requires=['clilib', 'requests'],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
        "Operating System :: OS Independent",
    ],
)
