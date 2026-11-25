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

    def swipe_row(self, dx, dy=0):
        box = self.page.locator(".book").first.bounding_box()
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        session = self.context.new_cdp_session(self.page)

        def touch(kind, points):
            session.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})

        touch("touchStart", [{"x": x, "y": y}])
        for step in range(1, 7):
            touch("touchMove", [{"x": x + dx * step / 6, "y": y + dy * step / 6}])
        touch("touchEnd", [])
        session.detach()

    def test_vertical_drag_and_reverse_swipe(self):
        remove = self.page.get_by_role("button", name="長編を削除")
        self.swipe_row(3, -90)
        expect(self.page.locator(".book-del")).not_to_be_in_viewport(ratio=0.01)
        expect(self.page.locator("#reader")).to_be_hidden()
        self.swipe_row(-120)
        expect(remove).to_be_in_viewport(ratio=0.95)
        self.swipe_row(120)
        expect(self.page.locator(".book-del")).not_to_be_in_viewport(ratio=0.01)
        self.page.locator(".book-open").tap()
        expect(self.page.locator("#reader")).to_be_visible()

    def test_scroll_a_long_shelf(self):
        page = self.page
        with page.expect_file_chooser() as chooser:
            page.locator("#addBtn").tap()
        chooser.value.set_files([
            {"name": f"本{i}.txt", "mimeType": "text/plain", "buffer": b"text"}
            for i in range(16)
        ])
        expect(page.locator(".book")).to_have_count(17)
        self.swipe_row(4, -120)
        page.wait_for_function("window.scrollY > 0")
        expect(page.locator(".book.swiped")).to_have_count(0)
        expect(page.locator("#reader")).to_be_hidden()

    def test_delete_while_another_tab_is_reading(self):
        reader = self.context.new_page()
        reader.goto(self.url)
        reader.locator(".book-open").tap()
        self.page.bring_to_front()

        remove = self.page.get_by_role("button", name="長編を削除", exact=True)
        expect(self.page.locator(".book-del")).not_to_be_in_viewport(ratio=0.01)
        self.swipe_row(-120)
        remove.tap()
        self.page.locator("#cancelDialog").tap()
        expect(self.page.locator(".book-open")).to_have_count(1)
        expect(self.page.locator(".book-del")).not_to_be_in_viewport(ratio=0.01)
        self.swipe_row(-120)
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
