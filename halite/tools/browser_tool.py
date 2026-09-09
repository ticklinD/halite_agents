"""
BrowserTool — open URL, wait for load, take full-page + viewport screenshots,
run DOM layout checks (§6.4, §6.2 visual review).

Uses Playwright headless Chromium. If Playwright browsers aren't installed,
reports clearly and skips (never silently faked — §5/§6.4).
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from halite.models.schemas import ToolResult, BrowserToolArgs
from halite.tools.base import BaseTool
from halite.utils.logging_config import logger


class BrowserTool(BaseTool):
    """Playwright-based browser automation and layout checking."""

    name = "browser"

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self._browser = None
        self._playwright = None
        self._page = None

    def validate_args(self, args: dict[str, Any]) -> bool:
        try:
            BrowserToolArgs(**args)
            return True
        except Exception:
            return False

    async def _ensure_browser(self):
        """Lazily instantiate the Playwright browser. Raises if unavailable."""
        if self._browser is not None:
            return self._browser
        try:
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(headless=True)
            logger.info("Playwright Chromium launched")
            return self._browser
        except Exception as exc:
            # Check if browsers are missing — guide user to install
            logger.error("Failed to launch Playwright: {}", str(exc))
            raise RuntimeError(
                f"Playwright browser unavailable: {exc}. "
                "Run 'playwright install chromium' to set it up (needs internet once). "
                "The browser step is skipped until then."
            )

    async def execute(self, args: dict[str, Any], project_root: Path | None = None) -> ToolResult:
        operation = args.get("operation")
        call_id = str(args.get("_call_id", ""))

        try:
            if operation == "open":
                return await self._open(args, call_id)
            elif operation == "screenshot":
                return await self._screenshot(args, call_id)
            elif operation == "dom_check":
                return await self._dom_check(args, call_id)
            else:
                return ToolResult(
                    tool_call_id=call_id, success=False, output="",
                    error=f"Unknown op: {operation}",
                )
        except RuntimeError as rex:
            # Playwright unavailable — skip clearly, not faked (§5)
            logger.warning("Browser tool skipped: {}", rex)
            return ToolResult(
                tool_call_id=call_id, success=False, output="",
                error=f"Browser unavailable: {rex}",
            )
        except Exception as exc:
            logger.exception("BrowserTool {} failed: {}", operation, str(exc))
            return ToolResult(
                tool_call_id=call_id, success=False, output="",
                error=f"Browser error: {exc}",
            )

    async def _open(self, args: dict[str, Any], call_id: str) -> ToolResult:
        timeout = args.get("timeout", 15)
        try:
            # Use the shared lazy-launch helper — no duplicated launch logic.
            browser = await self._ensure_browser()
            page = await browser.new_page()
            self._page = page

            await page.goto(args["url"], wait_until="load", timeout=timeout * 1000)
            title = await page.title()
            logger.info("Browser opened {} — title: {}", args["url"], title)
            return ToolResult(
                tool_call_id=call_id, success=True,
                output=f"Opened {args['url']} — title: {title}",
            )
        except Exception as exc:
            logger.error("Browser open failed for {}: {}", args["url"], str(exc))
            return ToolResult(
                tool_call_id=call_id, success=False, output="",
                error=f"Failed to open {args['url']}: {exc}",
            )

    async def _screenshot(self, args: dict[str, Any], call_id: str) -> ToolResult:
        if self._page is None:
            # Open first
            await self._open(args, call_id)

        try:
            full_page = args.get("full_page", True)
            shots = Path.home() / ".halite" / "screenshots"
            shots.mkdir(parents=True, exist_ok=True)

            # Full-page screenshot
            full_path = shots / f"page_{args['url'].replace('://','_').replace('/','_')}_full.png"
            await self._page.screenshot(path=str(full_path), full_page=full_page)
            return ToolResult(
                tool_call_id=call_id, success=True,
                output=f"Screenshot saved: {full_path}",
                artifacts=[str(full_path)],
            )
        except Exception as exc:
            logger.error("Screenshot failed: {}", str(exc))
            return ToolResult(
                tool_call_id=call_id, success=False, output="",
                error=f"Screenshot failed: {exc}",
            )

    async def _dom_check(self, args: dict[str, Any], call_id: str) -> ToolResult:
        """
        DOM-level layout checks (§6.2 step 5, §6.4):
        - elements overflowing the viewport
        - overlapping bounding boxes
        - zero-size elements that should have content
        """
        if self._page is None:
            await self._open(args, call_id)

        try:
            checks = await self._page.evaluate("""
                () => {
                    const issues = [];
                    const viewport = {
                        w: window.innerWidth,
                        h: window.innerHeight
                    };

                    const all = document.querySelectorAll('body *');
                    for (const el of all) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width === 0 && rect.height === 0) continue;
                        // Skip elements with no real size
                        if (rect.width < 2 && rect.height < 2) continue;

                        // 1. Overflow past viewport
                        if (rect.left < -5 || rect.right > viewport.w + 5 ||
                            rect.top < -5 || rect.bottom > viewport.h + 5) {
                            if (el.innerText && el.innerText.trim().length > 0) {
                                issues.push({
                                    type: 'overflow',
                                    tag: el.tagName,
                                    cls: el.className || '',
                                    id: el.id || '',
                                    text: (el.innerText || '').trim().slice(0,60),
                                    rect: {l: Math.round(rect.left), r: Math.round(rect.right),
                                           t: Math.round(rect.top), b: Math.round(rect.bottom)}
                                });
                            }
                        }

                        // 2. Zero-size that should have content
                        if ((rect.width < 1 || rect.height < 1) && el.innerText && el.innerText.trim()) {
                            issues.push({
                                type: 'zero_size',
                                tag: el.tagName,
                                cls: el.className || '',
                                id: el.id || '',
                                text: el.innerText.trim().slice(0,60)
                            });
                        }
                    }

                    // 3. Overlapping bounding boxes (heuristic — same-parent siblings)
                    const visible = [...document.querySelectorAll('body *')]
                        .filter(el => {
                            const r = el.getBoundingClientRect();
                            return r.width > 5 && r.height > 5 && r.top >= 0 && r.left >= 0;
                        });
                    for (let i = 0; i < visible.length; i++) {
                        const a = visible[i].getBoundingClientRect();
                        for (let j = i+1; j < visible.length; j++) {
                            const b = visible[j].getBoundingClientRect();
                            // Check overlap
                            const overlapW = Math.min(a.right, b.right) - Math.max(a.left, b.left);
                            const overlapH = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
                            if (overlapW > Math.min(a.width,b.width)*0.8 &&
                                overlapH > Math.min(a.height,b.height)*0.8 &&
                                visible[i] !== visible[j].parentElement &&
                                visible[j] !== visible[i].parentElement) {
                                issues.push({
                                    type: 'overlap',
                                    a: visible[i].tagName + '.' + (visible[i].className || ''),
                                    b: visible[j].tagName + '.' + (visible[j].className || ''),
                                    overlap: [Math.round(overlapW), Math.round(overlapH)]
                                });
                            }
                        }
                    }

                    return { issues, viewport };
                }
            """)

            issues = checks.get("issues", [])
            vp = checks.get("viewport", {})

            if not issues:
                logger.info("DOM check clean — viewport {}x{}", vp.get("w"), vp.get("h"))
                return ToolResult(
                    tool_call_id=call_id, success=True,
                    output=f"DOM layout check: CLEAN (viewport {vp.get('w')}x{vp.get('h')})",
                )

            # Group by type
            from collections import Counter
            counts = Counter(i["type"] for i in issues)
            summary = f"DOM layout issues found: {len(issues)}\n"
            summary += f"  overflow: {counts.get('overflow',0)}, overlap: {counts.get('overlap',0)}, zero_size: {counts.get('zero_size',0)}\n"
            for i in issues[:20]:
                if i["type"] == "overflow":
                    summary += f"  [overflow] <{i['tag']}> {i.get('text','')[:40]} at {i['rect']}\n"
                elif i["type"] == "zero_size":
                    summary += f"  [zero_size] <{i['tag']}> {i.get('text','')[:40]}\n"
                else:
                    summary += f"  [overlap] {i['a']} ↔ {i['b']}\n"

            return ToolResult(
                tool_call_id=call_id, success=True,
                output=summary,
            )

        except Exception as exc:
            logger.error("DOM check failed: {}", str(exc))
            return ToolResult(
                tool_call_id=call_id, success=False, output="",
                error=f"DOM check failed: {exc}",
            )

    async def close(self) -> None:
        """Close browser resources."""
        try:
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
        except Exception:
            pass
