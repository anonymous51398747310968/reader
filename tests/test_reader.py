"""Run with python -m unittest discover -s tests after installing Playwright and Chromium."""

import os
import unittest
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright


class ReaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = Path(__file__).resolve().parents[1]
        handler = partial(SimpleHTTPRequestHandler, directory=str(root))
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.addClassCleanup(server.server_close)
        Thread(target=server.serve_forever, daemon=True).start()
        cls.addClassCleanup(server.shutdown)
        cls.url = f"http://127.0.0.1:{server.server_port}/"

        playwright = sync_playwright().start()
        cls.addClassCleanup(playwright.stop)
        cls.browser = playwright.chromium.launch(
            executable_path=os.environ.get("CHROMIUM_PATH")
        )
        cls.addClassCleanup(cls.browser.close)

    def setUp(self):
        self.context = self.browser.new_context(
            has_touch=True, viewport={"width": 390, "height": 844}
        )
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.goto(self.url)
        with self.page.expect_file_chooser() as chooser:
            self.page.locator("#addBtn").tap()
        text = "# 冒頭\n\n" + ("本文を読む。" * 30 + "\n\n") * 80 + "# 結末"
        chooser.value.set_files(
            {"name": "長編.md", "mimeType": "text/markdown", "buffer": text.encode()}
        )
        expect(self.page.locator(".book-title")).to_have_text("長編")

    def test_delete_while_another_tab_is_reading(self):
        reader = self.context.new_page()
        reader.goto(self.url)
        reader.locator(".book-open").tap()

        remove = self.page.get_by_role("button", name="長編を削除", exact=True)
        remove.tap()
        self.page.locator("#cancelDialog").tap()
        expect(self.page.locator(".book-open")).to_have_count(1)
        remove.tap()
        self.page.locator("#saveDialog").tap()
        expect(self.page.locator(".book-open")).to_have_count(0)

        reader.locator("#backBtn").tap()
        expect(reader.locator("#empty")).to_be_visible()
        self.page.reload()
        expect(self.page.locator("#shelf")).not_to_have_attribute("inert", "")
        expect(self.page.locator(".book-open")).to_have_count(0)

    def test_switch_writing_direction_keeps_position(self):
        page = self.page
        page.locator(".book-open").tap()
        page.locator("#progSlider").fill("440")
        for direction in ("縦書き", "横書き", "縦書き"):
            page.locator("#setBtn").tap()
            page.get_by_role("button", name=direction, exact=True).tap()
            page.locator("#sheetBack").tap(position={"x": 5, "y": 5})
            expect(page.locator("#progPct")).to_have_text("44%")

        for value, heading in [("0", "冒頭"), ("1000", "結末")]:
            page.locator("#progSlider").fill(value)
            expect(page.get_by_role("heading", name=heading)).to_be_in_viewport()
