"""
Setup script for Inbox Arena development tools.
Installs the 'arena' CLI command for easy access.
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read README for long description
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text() if readme_path.exists() else ""

setup(
    name="inbox-arena",
    version="0.1.0",
    description="Inbox Arena - AI Agent Competition Framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="Inbox Arena Team",
    url="https://github.com/inbox-arena/inbox-arena",
    packages=find_packages(),
    python_requires=">=3.9",
    install_requires=[
        "fastapi>=0.68.0",
        "uvicorn>=0.15.0",
        "websockets>=10.0",
        "requests>=2.25.0",
        "pydantic>=1.8.0",
        "click>=8.0.0",
        "openai>=1.0.0",
        "PyJWT>=2.0.0",
        "cryptography>=3.4.0",
        "python-multipart>=0.0.5",
    ],
    extras_require={
        "dev": [
            "pytest>=6.0.0",
            "pytest-asyncio>=0.15.0",
            "black>=21.0.0",
            "flake8>=3.9.0",
            "mypy>=0.910",
        ]
    },
    entry_points={
        "console_scripts": [
            "arena=scripts.arena_cli:cli",
        ]
    },
    include_package_data=True,
    package_data={
        "": ["docs/*.md", "data/*.json"],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Games/Entertainment",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    keywords="ai, agents, competition, email, llm, openai",
)