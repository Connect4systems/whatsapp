from pathlib import Path

from setuptools import find_packages, setup

base_dir = Path(__file__).parent
version_ns = {}

with open(base_dir / "whatsapp" / "__init__.py", encoding="utf-8") as f:
    exec(f.read(), version_ns)

setup(
    name="whatsapp",
    version=version_ns["__version__"],
    description="WhatsApp automation app for Frappe and ERPNext",
    author="Connect4systems",
    author_email="info@connect4systems.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
)
