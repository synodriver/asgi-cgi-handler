# -*- coding: utf-8 -*-
import os
import re

from setuptools import find_packages, setup


def get_version() -> str:
    path = os.path.join(
        os.path.abspath(os.path.dirname(__file__)), "asgi_cgi", "version.py"
    )
    with open(path, "r", encoding="utf-8") as f:
        data = f.read()
    result = re.findall(r"(?<=__version__ = \")\S+(?=\")", data)
    return result[0]


def get_dis():
    with open("README.markdown", "r", encoding="utf-8") as f:
        return f.read()


packages = find_packages(exclude=("test", "tests.*", "test*"))


def main():
    version: str = get_version()

    dis = get_dis()
    setup(
        name="asgi-cgi-handler",
        version=version,
        url="https://github.com/synodriver/asgi-cgi-handler",
        packages=packages,
        keywords=["asyncio", "asgi", "cgi"],
        description="run cgi scripts inside asgi",
        long_description_content_type="text/markdown",
        long_description=dis,
        author="synodriver",
        author_email="diguohuangjiajinweijun@gmail.com",
        maintainer="synodriver",
        python_requires=">=3.8",
        install_requires=["starlette", "h11", "sse-starlette"],
        license="GPLv3",
        classifiers=[
            "Development Status :: 3 - Alpha",
            "Framework :: AsyncIO",
            "Operating System :: OS Independent",
            "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
            "Programming Language :: Python",
            "Programming Language :: Python :: 3.7",
            "Programming Language :: Python :: 3.8",
            "Programming Language :: Python :: 3.9",
            "Programming Language :: Python :: 3.10",
            "Programming Language :: Python :: Implementation :: CPython",
            "Programming Language :: Python :: Implementation :: PyPy",
        ],
        include_package_data=True,
    )


if __name__ == "__main__":
    main()
