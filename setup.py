# -*- coding: utf-8 -*-

from setuptools import setup

with open("README.md", "r", encoding="utf-8") as f:
    readme = f.read()

INSTALL_REQUIRE = [
    "feast>=0.15.0",
    "psycopg2-binary>=2.8.3",
    "pyarrow>=2.0.0",
]

DEV_REQUIRE = [
    "flake8",
    "black==19.10b0",
    "isort>=5",
    "mypy==0.790",
    "build==0.7.0",
    "twine==3.4.2",
]

setup(
    name="feast-postgres",
    version="0.2.1",
    author="Gunnar Sv Sigurbjörnsson",
    author_email="gunnar.sigurbjornsson@gmail.com",
    description="PostgreSQL registry, and online and offline store for Feast",
    long_description=readme,
    long_description_content_type="text/markdown",
    python_requires=">=3.7.0",
    url="https://github.com/nossrannug/feast-postgres",
    project_urls={
        "Bug Tracker": "https://github.com/nossrannug/feast-postgres/issues",
    },
    license='Apache License, Version 2.0',
    packages=["feast_postgres", "feast_postgres.online_stores", "feast_postgres.offline_stores"],
    install_requires=INSTALL_REQUIRE,
    extras_require={
        "dev": DEV_REQUIRE,
    },
    keywords=("feast featurestore postgres offlinestore onlinestore"),
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.7",
    ],
)
