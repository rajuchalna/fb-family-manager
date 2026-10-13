name: Build EXE

on:
  push:
    branches: [ main ]
  workflow_dispatch:

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install selenium webdriver-manager pyinstaller

      - name: Build EXE
        run: pyinstaller --onefile --windowed --name "FBFamilyManager" --collect-all selenium --collect-all webdriver_manager --collect-submodules selenium --collect-submodules webdriver_manager --hidden-import selenium --hidden-import selenium.webdriver --hidden-import selenium.webdriver.chrome --hidden-import selenium.webdriver.chrome.webdriver --hidden-import selenium.webdriver.chrome.service --hidden-import selenium.webdriver.chrome.options --hidden-import selenium.webdriver.common.by --hidden-import selenium.webdriver.common.keys --hidden-import selenium.webdriver.support.ui --hidden-import selenium.webdriver.support.expected_conditions --hidden-import webdriver_manager --hidden-import webdriver_manager.chrome --hidden-import webdriver_manager.core --hidden-import webdriver_manager.core.os_manager main.py

      - name: Upload EXE
        uses: actions/upload-artifact@v4
        with:
          name: FBFamilyManager-Windows
          path: dist/FBFamilyManager.exe
